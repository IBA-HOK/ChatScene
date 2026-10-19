'''The ego starts an unprotected left turn at an intersection while yielding to an oncoming car when the oncoming car's throttle malfunctions, leading to an unexpected acceleration and forcing the ego to quickly modify its turning path to avoid a collision.'''
Town = 'Town05'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

param OPT_ADV_SPEED = Range(5, 15)
param OPT_MALFUNCTION_THROTTLE = Range(0.8, 1.0)  # High throttle value simulating malfunction
param OPT_MALFUNCTION_DURATION = Range(20, 50)    # Duration of the malfunction in simulation steps

behavior AdvBehavior():
    # Initial normal driving behavior
    do FollowLaneBehavior(target_speed=globalParameters.OPT_ADV_SPEED) until (distance to self) < 50
    
    # Simulate unexpected acceleration due to throttle malfunction
    take SetThrottleAction(globalParameters.OPT_MALFUNCTION_THROTTLE)
    for _ in range(globalParameters.OPT_MALFUNCTION_DURATION):
        wait

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
# Parameters for the adversarial agent's position in the oncoming lane
param OPT_GEO_Y_DISTANCE = Range(10, 50)  # Distance ahead of the ego vehicle
param OPT_GEO_X_DISTANCE = Range(-8, -4)  # Lateral offset to the left (oncoming lane)

# Identify the oncoming lane (left lane relative to ego)
laneSec = network.laneSectionAt(ego)
oncomingLane = laneSec._laneToLeft.lane

# Calculate the spawn point in the oncoming lane
IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE
projectPt = Vector(*oncomingLane.centerline.project(IntSpawnPt.position).coords[0])
advHeading = oncomingLane.orientation[projectPt]

# Spawn the adversarial car in the oncoming lane, facing the ego vehicle
AdvAgent = Car at projectPt,
    with heading advHeading + 180 deg,  # Facing opposite to the lane direction (towards ego)
    with regionContainedIn None,
    with behavior AdvBehavior()