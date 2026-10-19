'''The ego vehicle is making an unprotected left turn; the adversarial vehicle approaches the intersection at a normal speed but then suddenly attempts to make a last-second right turn.'''
Town = 'Town05'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    while (distance to self) > 60:
        wait  # The adversarial vehicle waits until it is close enough to affect the ego's maneuver.
    do FollowTrajectoryBehavior(globalParameters.OPT_ADV_SPEED, advTrajectory) until (distance from self to egoTrajectory) < globalParameters.OPT_STEER_DISTANCE
    # Initiates a sudden right turn as it gets close to the intersection.
    while True:
        take SetSpeedAction(self.speed)  # Maintains its current speed
        take SetSteerAction(globalParameters.OPT_STEER)  # Executes a sharp turn

param OPT_ADV_SPEED = Range(5, 15)  # The speed at which the adversarial vehicle approaches the intersection.
param OPT_STEER_DISTANCE = Range(0, 4)  # The distance at which the adversarial vehicle starts its sudden maneuver.
param OPT_STEER = Range(0.5, 1.0)  # The intensity of the steering action, specifying the sharpness of the turn.

## MONITORS
monitor TrafficLights:
    freezeTrafficLights()
    while True:
        if withinDistanceToTrafficLight(ego, 100):
            setClosestTrafficLightStatus(ego, "green")
        if withinDistanceToTrafficLight(AdvAgent, 100):
            setClosestTrafficLightStatus(AdvAgent, "green")
        wait

intersection = Uniform(*filter(lambda i: i.is4Way and i.isSignalized, network.intersections))
egoInitLane = Uniform(*intersection.incomingLanes)
egoManeuver = Uniform(*filter(lambda m: m.type is ManeuverType.LEFT_TURN, egoInitLane.maneuvers))
egoTrajectory = [egoInitLane, egoManeuver.connectingLane, egoManeuver.endLane]
egoSpawnPt = OrientedPoint in egoManeuver.startLane.centerline

# Setting up the ego vehicle at the initial position
ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL

require 10 <= (distance to intersection) <= 40
# Parameters for the adversarial agent's position in the opposite lane
param OPT_GEO_X_DISTANCE = Range(-8, 0)  # Lateral offset to place agent in the opposite lane
param OPT_GEO_Y_DISTANCE = Range(10, 30) # Longitudinal distance ahead of ego

# Identify the lane section and the opposite lane
laneSec = network.laneSectionAt(ego)
oppositeLane = laneSec._laneToLeft.lane

# Create an intermediate point along the road direction to project onto the opposite lane
IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE

# Project the intermediate point onto the centerline of the opposite lane to get the exact spawn position
projectPt = Vector(*oppositeLane.centerline.project(IntSpawnPt.position).coords[0])
advHeading = oppositeLane.orientation[projectPt]

# Spawn the adversarial car in the opposite lane, facing the ego vehicle (oncoming)
AdvAgent = Car at projectPt,
    with heading advHeading + 180 deg,
    with regionContainedIn None,
    with behavior AdvBehavior()