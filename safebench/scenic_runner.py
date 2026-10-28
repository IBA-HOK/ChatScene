''' 
Date: 2023-01-31 22:23:17
LastEditTime: 2023-03-07 12:28:17
Description: 
    Copyright (c) 2022-2023 Safebench Team

    This work is licensed under the terms of the MIT license.
    For a copy, see <https://opensource.org/licenses/MIT>
'''

import copy
import os
import json
import glob
import random
import signal
import time
from contextlib import contextmanager

import numpy as np
import carla
import pygame
from tqdm import tqdm

from safebench.gym_carla.env_wrapper import VectorWrapper
from safebench.gym_carla.envs.render import BirdeyeRender
from safebench.gym_carla.replay_buffer import RouteReplayBuffer, PerceptionReplayBuffer

from safebench.agent import AGENT_POLICY_LIST
from safebench.scenario import SCENARIO_POLICY_LIST

from safebench.scenario.scenario_manager.carla_data_provider import CarlaDataProvider
from safebench.scenario.scenario_data_loader import ScenarioDataLoader, ScenicDataLoader
from safebench.scenario.tools.scenario_utils import scenario_parse, scenic_parse

from safebench.util.logger import Logger, setup_logger_kwargs
from safebench.util.metric_util import get_route_scores, get_perception_scores
from safebench.util.dsf import (
    DSFConfig,
    compute_scene_metrics,
    metrics_for_json,
    select_param_entries,
    select_scene_ids_with_info,
)
from safebench.util.avoidable_dsf import (
    AvoidableConfig,
    scene_features,
    select_param_entries_avoidable,
    select_scene_ids_avoidable,
)
from safebench.util.directional_dsf import (
    DirectionalConfig,
    scene_direction,
    select_directional,
)
from safebench.util.scenic_utils import ScenicSimulator


class _FenceTimeout(BaseException):
    def __init__(self, code):
        self.code = code


_fence_code = [42]


def _fence_alarm(signum, frame):
    raise _FenceTimeout(_fence_code[0])


@contextmanager
def carla_fence(seconds, desc, code=42):
    # SIGALRM interrupts a wedged synchronous CARLA RPC in the main thread;
    # the worker exits so the batch retries. code 42 = restart the server,
    # 43 = keep the warm server (setup-hang class).
    prev = signal.signal(signal.SIGALRM, _fence_alarm)
    _fence_code[0] = code
    signal.alarm(int(seconds))
    try:
        yield
    except _FenceTimeout as f:
        err = TimeoutError(f"{desc} exceeded {seconds}s")
        err.fence_code = f.code
        raise err
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev)


class ScenicRunner:
    def __init__(self, agent_config, scenario_config):
        self.scenario_config = scenario_config
        self.agent_config = agent_config

        self.seed = scenario_config['seed']
        self.exp_name = scenario_config['exp_name']
        self.output_dir = scenario_config['output_dir']
        self.mode = scenario_config['mode']
        self.save_video = scenario_config['save_video']

        self.render = scenario_config['render']
        self.num_scenario = scenario_config['num_scenario']
        self.fixed_delta_seconds = scenario_config['fixed_delta_seconds']
        self.scenario_category = scenario_config['scenario_category']

        self.selection_metric = str(
            scenario_config.get('selection_metric', 'collision')
        ).strip().lower()
        if self.selection_metric not in ('collision', 'dsf', 'dsf_avoidable', 'dsf_directional'):
            raise ValueError(
                f"Unsupported selection_metric: {self.selection_metric!r} "
                "(expected 'collision', 'dsf', 'dsf_avoidable', or 'dsf_directional')"
            )
        self.dsf_config = DSFConfig.from_mapping(scenario_config.get('dsf'))
        self.avoidable_config = AvoidableConfig.from_mapping(scenario_config.get('avoidable'))
        self.directional_config = DirectionalConfig.from_mapping(scenario_config.get('directional'))
        self.scene_map_dir = (
            scenario_config.get('scene_map_dir') or scenario_config['scenic_dir']
        )

        # wall-clock guard per episode so a wedged simulator can never hang a
        # run forever; override with 'episode_timeout' (seconds) in scenario yaml
        try:
            self.episode_timeout = float(scenario_config.get('episode_timeout', 600))
        except Exception:
            self.episode_timeout = 600

        # fences (seconds, env-tunable) for CARLA calls outside the episode
        # loop: cleanup/spawn/tick RPCs block forever on a wedged server
        self.fence_cleanup = int(os.environ.get('FENCE_CLEANUP', '300'))
        self.fence_setup = int(os.environ.get('FENCE_SETUP', '900'))
        self.fence_destroy = int(os.environ.get('FENCE_DESTROY', '120'))

        # continue training flag
        self.continue_agent_training = scenario_config['continue_agent_training']
        self.continue_scenario_training = scenario_config['continue_scenario_training']

        # apply settings to carla
        self.client = carla.Client('localhost', scenario_config['port'])
        self.client.set_timeout(10.0)
        self.world = None
        self.env = None

        self.env_params = {
            'auto_ego': scenario_config['auto_ego'],
            'obs_type': agent_config['obs_type'],
            'scenario_category': self.scenario_category,
            'ROOT_DIR': scenario_config['ROOT_DIR'],
            'warm_up_steps': 9,                                        # number of ticks after spawning the vehicles
            'disable_lidar': True,                                     # show bird-eye view lidar or not
            'display_size': 128,                                       # screen size of one bird-eye view window
            'obs_range': 32,                                           # observation range (meter)
            'd_behind': 12,                                            # distance behind the ego vehicle (meter)
            'max_past_step': 1,                                        # the number of past steps to draw
            'discrete': False,                                         # whether to use discrete control space
            'discrete_acc': [-3.0, 0.0, 3.0],                          # discrete value of accelerations
            'discrete_steer': [-0.2, 0.0, 0.2],                        # discrete value of steering angles
            'continuous_accel_range': [-3.0, 3.0],                     # continuous acceleration range
            'continuous_steer_range': [-0.3, 0.3],                     # continuous steering angle range
            'max_episode_step': scenario_config['max_episode_step'],   # maximum timesteps per episode
            'max_waypt': 12,                                           # maximum number of waypoints
            'lidar_bin': 0.125,                                        # bin size of lidar sensor (meter)
            'out_lane_thres': 4,                                       # threshold for out of lane (meter)
            'desired_speed': 8,                                        # desired speed (m/s)
            'image_sz': 1024,                                          # TODO: move to config of od scenario
        }


        # pass config from scenario to agent
        agent_config['mode'] = scenario_config['mode']
        agent_config['ego_action_dim'] = scenario_config['ego_action_dim']
        agent_config['ego_state_dim'] = scenario_config['ego_state_dim']
        agent_config['ego_action_limit'] = scenario_config['ego_action_limit']

        # define logger
        logger_kwargs = setup_logger_kwargs(
            self.exp_name, 
            self.output_dir, 
            self.seed,
            agent=agent_config['policy_type'],
            scenario=scenario_config['policy_type'],
            scenario_category=self.scenario_category
        )
        self.logger = Logger(**logger_kwargs)
        
        # prepare parameters
        if self.mode == 'train_agent':
            self.buffer_capacity = agent_config['buffer_capacity']
            self.eval_in_train_freq = agent_config['eval_in_train_freq']
            self.save_freq = agent_config['save_freq']
            self.train_episode = agent_config['train_episode']
            self.current_episode = -1
            self.logger.save_config(agent_config)
            self.logger.create_training_dir()
        elif self.mode == 'train_scenario':
            self.save_freq = agent_config['save_freq']
            self.logger.create_eval_dir(load_existing_results=False)
        elif self.mode == 'eval':
            self.save_freq = 1
            self.logger.log('>> Evaluation Mode, skip config saving', 'yellow')
            self.logger.create_eval_dir(load_existing_results=False)
        else:
            raise NotImplementedError(f"Unsupported mode: {self.mode}.")

        # define agent and scenario
        self.logger.log('>> Agent Policy: ' + agent_config['policy_type'])
        self.logger.log('>> Scenario Policy: ' + scenario_config['policy_type'])

        if self.scenario_config['auto_ego']:
            self.logger.log('>> Using auto-polit for ego vehicle, action of policy will be ignored', 'yellow')
        if scenario_config['policy_type'] == 'ordinary' and self.mode != 'train_agent':
            self.logger.log('>> Ordinary scenario can only be used in agent training', 'red')
            raise Exception()
        self.logger.log('>> ' + '-' * 40)

        # define agent and scenario policy (model loading can stall on storage)
        with carla_fence(self.fence_setup, 'policy_init', 43):
            self.agent_policy = AGENT_POLICY_LIST[agent_config['policy_type']](agent_config, logger=self.logger)
            self.scenario_policy = SCENARIO_POLICY_LIST[scenario_config['policy_type']](scenario_config, logger=self.logger)
        if self.save_video:
            assert self.mode == 'eval', "only allow video saving in eval mode"
            self.logger.init_video_recorder()

    def _init_world(self):
        self.logger.log(">> Initializing carla world")
        self.world = self.client.get_world()
        settings = self.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = self.fixed_delta_seconds
        self.world.apply_settings(settings)
        CarlaDataProvider.set_client(self.client)
        CarlaDataProvider.set_world(self.world)
        CarlaDataProvider.set_traffic_manager_port(self.scenario_config['tm_port'])
        
    def _init_scenic(self, config):
        self.logger.log(f">> Initializing scenic simulator: {config.scenic_file}")
        self.scenic = ScenicSimulator(config.scenic_file, config.extra_params)
        
    def _init_renderer(self):
        self.logger.log(">> Initializing pygame birdeye renderer")
        pygame.init()
        flag = pygame.HWSURFACE | pygame.DOUBLEBUF
        if not self.render:
            flag = flag | pygame.HIDDEN
        if self.scenario_category in ['planning', 'scenic']: 
            # [bird-eye view, Lidar, front view] or [bird-eye view, front view]
            if self.env_params['disable_lidar']:
                window_size = (self.env_params['display_size'] * 2, self.env_params['display_size'] * self.num_scenario)
            else:
                window_size = (self.env_params['display_size'] * 3, self.env_params['display_size'] * self.num_scenario)
        else:
            window_size = (self.env_params['display_size'], self.env_params['display_size'] * self.num_scenario)
        self.display = pygame.display.set_mode(window_size, flag)

        # initialize the render for generating observation and visualization
        pixels_per_meter = self.env_params['display_size'] / self.env_params['obs_range']
        pixels_ahead_vehicle = (self.env_params['obs_range'] / 2 - self.env_params['d_behind']) * pixels_per_meter
        self.birdeye_params = {
            'screen_size': [self.env_params['display_size'], self.env_params['display_size']],
            'pixels_per_meter': pixels_per_meter,
            'pixels_ahead_vehicle': pixels_ahead_vehicle,
        }
        self.birdeye_render = BirdeyeRender(self.world, self.birdeye_params, logger=self.logger)

    def run_scenes(self, scenes):
        self.logger.log(f">> Begin to run the scene...")
        ## currently there is only one scene in this list ##
        for scene in scenes:
            if self.scenic.setSimulation(scene):
                self.scenic.update_behavior = self.scenic.runSimulation()
                next(self.scenic.update_behavior)
        
    def _fence_bail(self, e):
        code = getattr(e, 'fence_code', 42)
        self.logger.log(f">> {e}; aborting worker for batch retry (exit {code}).", color='red')
        raise SystemExit(code)

    def train(self, data_loader, start_episode=0, replay_buffer = None):
        # general buffer for both agent and scenario

        for _ in tqdm(range(len(data_loader))):
            self.current_episode += 1
            if self.current_episode >= self.train_episode:
                return
            if self.current_episode < start_episode:
                continue
            # sample scenarios
            sampled_scenario_configs, _ = data_loader.sampler()
            # reset the index counter to create endless loader
            # data_loader.reset_idx_counter()
            
            scenes = [config.scene for config in sampled_scenario_configs]
            # begin to run the scene
            with carla_fence(self.fence_setup, 'run_scenes', 43):
                self.run_scenes(scenes)
            
            # get static obs and then reset with init action 
            static_obs = self.env.get_static_obs(sampled_scenario_configs)
            self.scenario_policy.load_model(sampled_scenario_configs)
            scenario_init_action, additional_dict = self.scenario_policy.get_init_action(static_obs)
            with carla_fence(self.fence_setup, 'env.reset', 43):
                obs, infos = self.env.reset(sampled_scenario_configs, scenario_init_action)
            replay_buffer.store_init([static_obs, scenario_init_action], additional_dict=additional_dict)

            # get ego vehicle from scenario
            self.agent_policy.set_ego_and_route(self.env.get_ego_vehicles(), infos)

            # start loop
            episode_reward = []
            episode_start = time.time()
            while not self.env.all_scenario_done():
                if time.time() - episode_start > self.episode_timeout:
                    self.logger.log(f">> Episode wall-clock timeout ({self.episode_timeout:.0f}s), forcing done.", color='red')
                    break
                # get action from agent policy and scenario policy (assume using one batch)
                ego_actions = self.agent_policy.get_action(obs, infos, deterministic=False)
                scenario_actions = self.scenario_policy.get_action(obs, infos, deterministic=False)

                # apply action to env and get obs
                next_obs, rewards, dones, infos = self.env.step(ego_actions=ego_actions, scenario_actions=scenario_actions)
                replay_buffer.store([ego_actions, scenario_actions, obs, next_obs, rewards, dones], additional_dict=infos)
                obs = copy.deepcopy(next_obs)
                episode_reward.append(np.mean(rewards))

            # train off-policy agent or scenario
            if self.mode == 'train_agent' and self.agent_policy.type == 'offpolicy':
                loss = self.agent_policy.train(replay_buffer)
            elif self.mode == 'train_scenario' and self.scenario_policy.type == 'offpolicy':
                self.scenario_policy.train(replay_buffer)
                
            score_function = get_route_scores if self.scenario_category in ['planning', 'scenic'] else get_perception_scores
            all_scores = score_function(self.env.running_results)

            # end up environment
            with carla_fence(self.fence_cleanup, 'env.clean_up'):
                self.env.clean_up()
            replay_buffer.finish_one_episode()
            self.logger.add_training_results('episode', self.current_episode)
            self.logger.add_training_results('episode_reward', np.sum(episode_reward))
            for key, value in all_scores.items():
                self.logger.add_training_results(key, value)
            if loss is not None:
                critic_loss, actor_loss = loss
                self.logger.add_training_results('critic_loss', critic_loss)
                self.logger.add_training_results('actor_loss', actor_loss)
            else:
                critic_loss, actor_loss = 0, 0
                self.logger.add_training_results('critic_loss', critic_loss)
                self.logger.add_training_results('actor_loss', actor_loss)  
            self.logger.log(f">> Episode: {self.current_episode}, #buffer_len: {replay_buffer.buffer_len}, critic: {critic_loss:.3f}, actor: {actor_loss:.3f}")
            self.logger.save_training_results()

            # train on-policy agent or scenario
            if self.mode == 'train_agent' and self.agent_policy.type == 'onpolicy':
                self.agent_policy.train(replay_buffer)
            elif self.mode == 'train_scenario' and self.scenario_policy.type in ['init_state', 'onpolicy']:
                self.scenario_policy.train(replay_buffer)

            # eval during training
            if (self.current_episode+1) % self.eval_in_train_freq == 0:
                #self.eval(env, data_loader)
                pass

            # save checkpoints
            if (self.current_episode+1) % self.save_freq == 0:
                if self.mode == 'train_agent':
                    self.agent_policy.save_model(self.current_episode, replay_buffer)
                if self.mode == 'train_scenario':
                    self.scenario_policy.save_model(self.current_episode)
        
        with carla_fence(self.fence_destroy, 'scenic.destroy'):
            self.scenic.destroy()
        
    def eval(self, data_loader, select = False):
        num_finished_scenario = 0
        data_loader.reset_idx_counter()
        # recording the score and the id of corresponding selected scenes
        map_id_score = {}
        dsf_entries = []
        self._last_dsf_info = None
        self._last_avoidable_info = None
        self._last_directional_info = None
        score_function = (
            get_route_scores
            if self.scenario_category in ['planning', 'scenic']
            else get_perception_scores
        )
        behavior_name = data_loader.behavior
        route_id = data_loader.route_id
        opt_step = data_loader.opt_step
        opt_time = 0
        
        if route_id is None:
            log_name = f'OPT_{behavior_name}'
        else:
            log_name = f'OPT_{behavior_name}_ROUTE-{route_id}'
            
        if select:
            self.scene_map[log_name] = {}
            self.scene_map[log_name][f'opt_time_{opt_time}'] = self.scenic.save_params()
            
        try:
            while len(data_loader) > 0:
                # sample scenarios
                sampled_scenario_configs, num_sampled_scenario = data_loader.sampler()
                num_finished_scenario += num_sampled_scenario
                assert num_sampled_scenario == 1, 'scenic can only run one scene at one time'

                scenes = [config.scene for config in sampled_scenario_configs]
                # begin to run the scene
                with carla_fence(self.fence_setup, 'run_scenes', 43):
                    self.run_scenes(scenes)

                # reset envs with new config, get init action from scenario policy, and run scenario
                static_obs = self.env.get_static_obs(sampled_scenario_configs)
                self.scenario_policy.load_model(sampled_scenario_configs)
                scenario_init_action, _ = self.scenario_policy.get_init_action(static_obs, deterministic=True)
                with carla_fence(self.fence_setup, 'env.reset', 43):
                    obs, infos = self.env.reset(sampled_scenario_configs, scenario_init_action)

                # get ego vehicle from scenario
                self.agent_policy.set_ego_and_route(self.env.get_ego_vehicles(), infos)

                score_list = {s_i: [] for s_i in range(num_sampled_scenario)}
                episode_start = time.time()
                while not self.env.all_scenario_done():
                    if time.time() - episode_start > self.episode_timeout:
                        self.logger.log(f">> Episode wall-clock timeout ({self.episode_timeout:.0f}s), forcing done.", color='red')
                        break
                    # get action from agent policy and scenario policy (assume using one batch)
                    ego_actions = self.agent_policy.get_action(obs, infos, deterministic=True)
                    scenario_actions = self.scenario_policy.get_action(obs, infos, deterministic=True)

                    # apply action to env and get obs
                    obs, rewards, _, infos = self.env.step(ego_actions=ego_actions, scenario_actions=scenario_actions)

                    # save video
                    if self.save_video:
                        if self.scenario_category in ['planning', 'scenic']:
                            self.logger.add_frame(pygame.surfarray.array3d(self.display).transpose(1, 0, 2))
                        else:
                            self.logger.add_frame({s_i['scenario_id']: ego_actions[n_i]['annotated_image'] for n_i, s_i in enumerate(infos)})

                    # accumulate scores of corresponding scenario
                    reward_idx = 0
                    for s_i in infos:
                        score = rewards[reward_idx] if self.scenario_category in ['planning', 'scenic'] else 1-infos[reward_idx]['iou_loss']
                        score_list[s_i['scenario_id']].append(score)
                        reward_idx += 1

                # clean up all things
                self.logger.log(">> All scenarios are completed. Clearning up all actors")
                with carla_fence(self.fence_cleanup, 'env.clean_up'):
                    self.env.clean_up()

                # save video
                if self.save_video:
                    data_ids = [config.data_id for config in sampled_scenario_configs]
                    self.logger.save_video(data_ids=data_ids, log_name= log_name)

                # print score for ranking
                self.logger.log(f'[{num_finished_scenario}/{data_loader.num_total_scenario}] Ranking scores for batch scenario:', color='yellow')
                for s_i in score_list.keys():
                    self.logger.log('\t Env id ' + str(s_i) + ': ' + str(np.mean(score_list[s_i])), color='yellow')

                # calculate evaluation results
                all_running_results = self.logger.add_eval_results(records=self.env.running_results)
                all_scores = score_function(all_running_results)
                self.logger.add_eval_results(scores=all_scores)
                self.logger.print_eval_results()
                self.logger.save_eval_results(log_name)

                if select and self.selection_metric == 'dsf_directional':
                    data_id = sampled_scenario_configs[0].data_id
                    sequence = all_running_results.get(data_id)
                    if sequence:
                        params = dict(getattr(sampled_scenario_configs[0].scene, 'params', {}) or {})
                        features = scene_direction(sequence, self.directional_config)
                        dsf_entries.append({'data_id': data_id, 'features': features, 'params': params})
                        if infos[0]['collision']:
                            self.scenic.record_params()
                        self.logger.log(
                            f">> Directional DSF data_id={data_id}: "
                            f"status={features.status} front={features.front_dsf:.4g} "
                            f"ratio={features.front_ratio:.3g}", color='yellow')
                    else:
                        self.logger.log(f">> Directional DSF data_id={data_id}: missing record, skipped", color='red')
                elif select and self.selection_metric in ('dsf', 'dsf_avoidable'):
                    data_id = sampled_scenario_configs[0].data_id
                    sequence = all_running_results.get(data_id)
                    if sequence:
                        metrics = compute_scene_metrics(sequence, self.dsf_config)
                        params = dict(
                            getattr(sampled_scenario_configs[0].scene, 'params', {}) or {}
                        )
                        entry = {
                            'data_id': data_id,
                            'metrics': metrics,
                            'params': params,
                        }
                        if self.selection_metric == 'dsf_avoidable':
                            features = scene_features(sequence, self.avoidable_config)
                            entry['features'] = features
                            self.logger.log(
                                f">> Avoidable DSF data_id={data_id}: "
                                f"status={features.status} margin={features.margin_m:.3g} "
                                f"soft={features.soft_score:.4g} "
                                f"ratio={features.front_ratio:.3g}",
                                color='yellow',
                            )
                        else:
                            self.logger.log(
                                f">> DSF data_id={data_id}: dsf={metrics['dsf_max']:.4g} "
                                f"ttc={metrics['ttc_min']:.4g} drac={metrics['drac_max']:.4g} "
                                f"feasible={metrics['feasible']}",
                                color='yellow',
                            )
                        dsf_entries.append(entry)
                    else:
                        self.logger.log(
                            f">> DSF data_id={data_id}: missing record, skipped",
                            color='red',
                        )
                elif infos[0]['collision']:
                    self.scenic.record_params()

                if select and (num_finished_scenario % opt_step == 0):
                    opt_time += 1
                    if self.selection_metric == 'dsf_avoidable' and self.dsf_config.param_update:
                        chosen, param_info = select_param_entries_avoidable(
                            dsf_entries, self.dsf_config, self.avoidable_config
                        )
                        for entry in chosen:
                            self.scenic.record_params_values(entry['params'])
                        self.logger.log(
                            f">> Avoidable DSF param update: source={param_info['source']} "
                            f"k={param_info['k']} pool={param_info['pool']} "
                            f"avoidable={param_info['avoidable']}",
                            color='yellow',
                        )
                        dsf_entries = []
                    elif self.selection_metric == 'dsf' and self.dsf_config.param_update:
                        chosen, param_info = select_param_entries(
                            dsf_entries, self.dsf_config
                        )
                        for entry in chosen:
                            self.scenic.record_params_values(entry['params'])
                        self.logger.log(
                            f">> DSF param update: source={param_info['source']} "
                            f"k={param_info['k']} feasible={param_info['feasible']}",
                            color='yellow',
                        )
                        dsf_entries = []
                    self.scenic.update_params()
                    if self.selection_metric == 'dsf_avoidable' and self.avoidable_config.reset_opt_record:
                        self.scenic.reset_opt_record()
                    self.scene_map[log_name][f'opt_time_{opt_time}'] = self.scenic.save_params()
                    data_loader.train_scene(opt_time)
        finally:
            self.logger.save_eval_results(log_name)
        
        if select:
            self.scene_map[log_name]['select_id'] = self.select_adv_scene(
                self.logger.eval_records, score_function, data_loader.select_num
            )
            if self.selection_metric == 'dsf_directional' and self._last_directional_info is not None:
                self.scene_map[log_name]['directional_selection'] = self._last_directional_info
            elif self.selection_metric == 'dsf_avoidable' and self._last_avoidable_info is not None:
                info = self._last_avoidable_info
                self.scene_map[log_name]['avoidable_selection'] = info
            elif self.selection_metric == 'dsf' and self._last_dsf_info is not None:
                info = self._last_dsf_info
                self.scene_map[log_name]['dsf_selection'] = {
                    'config': info['config'],
                    'top_k': info['top_k'],
                    'feasible_count': info['feasible_count'],
                    'filled_from_all_feasible': info['filled_from_all_feasible'],
                    'fallback_non_collision': info['fallback_non_collision'],
                    'fallback_legacy': info['fallback_legacy'],
                    'selected': info['selected'],
                    'metrics': {
                        str(data_id): metrics_for_json(metrics)
                        for data_id, metrics in info['metrics'].items()
                    },
                }
            self.scene_map[log_name]['pinned'] = data_loader.capture_pinned(self.scene_map[log_name]['select_id'])
            self.dump_scene_map(sampled_scenario_configs[0].scenario_id)
            
        self.logger.clear()
        with carla_fence(self.fence_destroy, 'scenic.destroy'):
            self.scenic.destroy()
    
    def select_adv_scene(self, results, score_function, select_num):
        if self.selection_metric == 'dsf_directional':
            selected, info = select_directional(results, select_num, self.directional_config, score_function)
            self._last_directional_info = info
            self.logger.log(
                f">> Directional DSF selection: source={info['source']} "
                f"selected={info['selected']} status={info['status']} "
                f"front={info['front_dsf']} ratio={info['front_ratio']}", color='yellow')
            return selected
        if self.selection_metric == 'dsf_avoidable':
            selected, info = select_scene_ids_avoidable(
                results, select_num, self.avoidable_config, self.dsf_config, score_function
            )
            self._last_avoidable_info = info
            self.logger.log(
                f">> Avoidable DSF selection: source={info['source']} "
                f"selected={info['selected']} status={info['status']} "
                f"margin={info['margin']} counts={info['counts']}",
                color='yellow',
            )
            return selected
        if self.selection_metric == 'dsf':
            selected, info = select_scene_ids_with_info(
                results, select_num, self.dsf_config, score_function
            )
            self._last_dsf_info = info
            self.logger.log(
                f">> DSF selection: top_k={info['top_k']} "
                f"feasible={info['feasible_count']} selected={info['selected']} "
                f"filled_all_feasible={info['filled_from_all_feasible']} "
                f"fallback_non_collision={info['fallback_non_collision']} "
                f"fallback_legacy={info['fallback_legacy']}",
                color='yellow',
            )
            return selected

        # define your own selection mechanism here
        map_id_score_collision = {}
        map_id_score_non_collision = {}
        for i in results.keys():
            score = score_function({i:results[i]})
            if score['collision_rate'] == 1:
                map_id_score_collision[i] = score['final_score']
            else:
                map_id_score_non_collision[i] = score['final_score']

        # Sort the collision scenes by their scores
        collision_scenes_sorted = sorted(map_id_score_collision.items(), key=lambda x: x[1])

        # Get the number of scenes to select from the collision cases
        num_collision_selected = min(select_num, len(collision_scenes_sorted))

        # Select the lowest scored scenes with collision
        selected_scene_id = [scene[0] for scene in collision_scenes_sorted[:num_collision_selected]]

        # If not enough collision scenes, select remaining scenes
        num_non_collision_selected = select_num - num_collision_selected
        if num_non_collision_selected > 0:
            # Sort the non-collision scenes by their scores
            non_collision_scenes_sorted = sorted(map_id_score_non_collision.items(), key=lambda x: x[1])
            # Select the lowest scored scenes from the non-collision cases
            selected_scene_id.extend([scene[0] for scene in non_collision_scenes_sorted[:num_non_collision_selected]])
        return sorted(selected_scene_id)

    def run(self, test_epoch = None):
        # get scenario data of different maps
        try:
            with carla_fence(self.fence_setup, 'run_setup', 43):
                config_list = scenic_parse(self.scenario_config, self.logger)


                ### load rl model ##
                if self.mode == 'train_scenario':
                    ## we only need the pretrained surrogate model here ##
                    pass
                elif self.mode == 'train_agent':
                    ### initlize buffer ###
                    Buffer = RouteReplayBuffer if self.scenario_category in ['scenic', 'planning'] else PerceptionReplayBuffer
                    replay_buffer = Buffer(self.num_scenario, self.mode, self.buffer_capacity)

                    ### repeat the training, 20 is just a random placeholder
                    config_list = config_list * 20

                    ### check if resume ###
                    if self.continue_agent_training:
                        self.logger.load_training_results()
                        start_episode = self.check_continue_training(self.agent_policy, replay_buffer) + 1
                        if start_episode >= self.train_episode:
                            return
                    else:
                        self.clean_cache(self.agent_policy.model_path)
                        start_episode = -1

                elif self.mode == 'eval':
                    ### load trained model for evaluation ###
                    if test_epoch:
                        self.agent_policy.load_model(episode=test_epoch)
        except TimeoutError as e:
            self._fence_bail(e)
            
        last_town = None
        for config in config_list:
            
            ## set log name ##
            if config.route_id is None:
                log_name = f'OPT_{config.behavior}'
            else:
                log_name = f'OPT_{config.behavior}_ROUTE-{config.route_id}'
            
            ## check if all done ##
            if self.mode == 'train_scenario':
                self.scene_map = self.load_scene_map(config.scenario_id)
                entry = self.scene_map.get(log_name, {})
                # replay needs pinned per-scene values; entries selected
                # before pinning existed must be regenerated
                if 'select_id' in entry and entry.get('pinned'):
                    self.logger.log(f">> {log_name} already selected, skipping.")
                    continue
            if self.mode == 'eval':
                self.scene_map = self.load_scene_map(config.scenario_id)
                entry = self.scene_map.get(log_name, {})
                if 'select_id' in entry and entry.get('pinned'):
                    if self.logger.is_eval_complete(log_name, config.select_num, entry):
                        self.logger.log(f">> This scenario and route have been done.")
                        continue
                else:
                    cnt = self.logger.check_eval_dir(log_name)
                    if cnt != 0:
                        self.logger.log(f">> fossil detection: {log_name} missing pinned but has {cnt} records, renaming to fossil.", 'yellow')
                        try:
                            self.logger._rename_fossil(self.logger.record_file)
                            self.logger._rename_fossil(self.logger.result_file)
                        except (OSError, IOError):
                            pass
                    # also let is_eval_complete handle count-mismatch fossil rename
                    if cnt == config.select_num:
                        # len==select_num but missing pinned => force re-eval (not skip)
                        pass
                    elif cnt != 0 and cnt != config.select_num:
                        self.logger.is_eval_complete(log_name, config.select_num)
            elif self.mode == 'train_agent': 
                if self.current_episode >= self.train_episode - 1:
                    return
                
                if self.current_episode + config.select_num < start_episode:
                    self.current_episode += config.select_num
                    continue
                
            # initialize scenic and world (fenced: server setup RPCs can wedge)
            try:
                with carla_fence(self.fence_setup, 'init_scenic', 43):
                    self._init_scenic(config)

                # initialize map and render
                if last_town != config.extra_params['town']:
                    with carla_fence(self.fence_setup, 'init_world', 43):
                        self._init_world()
                        self._init_renderer()
                    last_town = config.extra_params['town']
            except TimeoutError as e:
                self._fence_bail(e)
            self.world.scenic = self.scenic
                
            # create scenarios within the vectorized wrapper
            self.env = VectorWrapper(
                self.env_params, 
                self.scenario_config, 
                self.world, 
                self.birdeye_render, 
                self.display, 
                self.logger
            )
            
            # prepare data loader and buffer
            # generation failures skip only this config; anything else re-raises
            try:
                with carla_fence(self.fence_setup, 'data_loader', 43):
                    data_loader = ScenicDataLoader(self.scenic, config, self.num_scenario)
                # run with different modes

                if self.mode == 'train_scenario':
                    ### select hard scenic scenario config on the surrogate model ###
                    self.scene_map = self.load_scene_map(config.scenario_id)
                    self.agent_policy.set_mode('eval')
                    self.scenario_policy.set_mode('eval')
                    self.eval(data_loader, select = True)
                    if os.environ.get("DUMP_ALL_PARAMS") == "1":
                        dump_path = os.path.join(
                            self.scene_map_dir,
                            f"scenario_{config.scenario_id}",
                            f"{log_name}_all_params.json",
                        )
                        data_loader.dump_all_params(dump_path)
                elif self.mode == 'train_agent':
                    ### train the surrogate model on the selected hard scenrios ###
                    self.agent_policy.set_mode('train')
                    self.scenario_policy.set_mode('eval')
                    self.train(data_loader, start_episode, replay_buffer)
                elif self.mode == 'eval':
                    ### evaluate the trained agent on different test models ###
                    self.agent_policy.set_mode('eval')
                    self.scenario_policy.set_mode('eval')
                    self.eval(data_loader)
                else:
                    raise NotImplementedError(f"Unsupported mode: {self.mode}.")
            except RuntimeError as e:
                if 'SCENIC_GEN_FAILED' not in str(e):
                    raise
                self.logger.log(f">> Skipping {log_name}: {e}", color='red')
                continue
            except TimeoutError as e:
                # fenced CARLA call wedged: abort the worker with a special
                # code so the batch retries this step with a fresh server
                self._fence_bail(e)

    def check_continue_training(self, policy, replay_buffer):
        # load previous checkpoint
        policy.load_model(replay_buffer = replay_buffer)
        if policy.continue_episode == 0:
            start_episode = 0
            self.logger.log('>> Previous checkpoint not found. Training from scratch.')
        else:
            start_episode = policy.continue_episode
            self.logger.log(f'>> Continue training from previous checkpoint, epoch: {start_episode}.')
        return start_episode
    
    def dump_scene_map(self, scenario_id):
        scenic_dir = os.path.join(
            self.scene_map_dir, f'scenario_{scenario_id}'
        )
        os.makedirs(scenic_dir, exist_ok=True)
        with open(os.path.join(scenic_dir, f'scenario_{scenario_id}.json'), 'w') as f:
            json.dump(self.scene_map, f, indent=4)

    def load_scene_map(self, scenario_id):
        scenic_dir = os.path.join(
            self.scene_map_dir, f'scenario_{scenario_id}'
        )
        try:
            with open(os.path.join(scenic_dir, f'scenario_{scenario_id}.json'), 'r') as f:
                data = json.load(f)
        except Exception:
            data = {}
        return data

    def clean_cache(self, path):
        # Get a list of all files in directory
        all_files = glob.glob(os.path.join(path, '*'))

        # Specify the file to keep
        file_to_keep = os.path.join(path, 'model.sac.-001.torch')

        # Remove all files except the one to keep
        for file in all_files:
            if file != file_to_keep:
                os.remove(file)
                
    def close(self):
        pygame.quit() # close pygame renderer
        if self.env:
            with carla_fence(self.fence_cleanup, 'env.clean_up', 42):
                self.env.clean_up()
            
    
