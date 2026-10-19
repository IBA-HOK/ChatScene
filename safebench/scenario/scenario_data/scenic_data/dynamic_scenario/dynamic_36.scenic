'''The ego vehicle is approaching the intersection; the adversarial car (on the right) suddenly accelerates and enters the intersection first and suddenly stop.'''
Town = 'Town05'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    while (distance to self) > 60:
        wait  # The adversarial vehicle waits until it is close enough to impact the ego's maneuver.
    do FollowTrajectoryBehavior(globalParameters.OPT_ADV_SPEED, advTrajectory) until (distance to self) < globalParameters.OPT_ADV_DISTANCE or (distance from self to egoTrajectory) < globalParameters.OPT_STOP_DISTANCE
    # Accelerates to enter the intersection first.
    while (distance from self to egoTrajectory) > globalParameters.OPT_STOP_DISTANCE:
        take SetThrottleAction(globalParameters.OPT_THROTTLE)  # Applies throttle to increase speed.
    # Once close enough, it decelerates abruptly.
    while True:
        take SetSpeedAction(0)  # Initiates a sudden stop.

param OPT_ADV_SPEED = Range(5, 15)  # The speed at which the adversarial vehicle approaches.
param OPT_ADV_DISTANCE = Range(0, 25)  # The proximity within which the acceleration is triggered.
param OPT_THROTTLE = Range(0.5, 1.0)  # The intensity of the throttle during the acceleration.
param OPT_STOP_DISTANCE = Range(0, 4)  # The critical distance at which the adversarial vehicle begins its deceleration.
intersection = Uniform(*filter(lambda i: i.is4Way or i.is3Way, network.intersections))
egoManeuver = Uniform(*filter(lambda m: m.type is ManeuverType.STRAIGHT, intersection.maneuvers))
egoInitLane = egoManeuver.startLane
egoTrajectory = [egoInitLane, egoManeuver.connectingLane, egoManeuver.endLane]
egoSpawnPt = OrientedPoint in egoInitLane.centerline

ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
# Defining adversarial maneuvers as those conflicting with the ego's straight path
advManeuvers = filter(lambda i: i.type == ManeuverType.RIGHT_TURN, egoManeuver.conflictingManeuvers)
advManeuver = Uniform(*advManeuvers)
advTrajectory = [advManeuver.startLane, advManeuver.connectingLane, advManeuver.endLane]
advSpawnPt = advManeuver.connectingLane.centerline[0]  # Initial point on the connecting lane's centerline
IntSpawnPt = advManeuver.connectingLane.centerline.start  # Start of the connecting lane centerline

param OPT_GEO_Y_DISTANCE = Range(-10, 10)
# Setting up the adversarial agent
AdvAgent = Car following roadDirection from IntSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE,
    with heading IntSpawnPt.heading,
    with regionContainedIn None,
    with behavior AdvBehavior()

# Requirements to ensure the adversarial agent's relative position and trajectory are correctly aligned with the scenario's needs
require 160 deg <= abs(RelativeHeading(AdvAgent)) <= 180 deg
require any([AdvAgent.position in traj for traj in [advManeuver.startLane, advManeuver.connectingLane, advManeuver.endLane]])