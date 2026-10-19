'''The ego attempts an unprotected left turn at an intersection while yielding to an oncoming car when the oncoming car veer erratically.'''
Town = 'Town05'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

param OPT_ADV_SPEED = Range(5, 15)
param OPT_ADV_STEER = Range(-1, 1)
param OPT_WAIT_STEER = Range(5, 20)

behavior AdvBehavior():
    do FollowLaneBehavior(target_speed=globalParameters.OPT_ADV_SPEED)
    
    while True:
        take SetSteerAction(globalParameters.OPT_ADV_STEER)
        for _ in range(globalParameters.OPT_WAIT_STEER):
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
param OPT_GEO_X_DISTANCE = Range(-8, 0)  # Lateral offset to place agent in oncoming lane
param OPT_GEO_Y_DISTANCE = Range(10, 50) # Distance ahead of ego in the oncoming lane

# Identify the oncoming lane (left lane relative to ego's direction)
laneSec = network.laneSectionAt(ego)
oncomingLane = laneSec._laneToLeft.lane

# Calculate spawn point in the oncoming lane
IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE
projectPt = Vector(*oncomingLane.centerline.project(IntSpawnPt.position).coords[0])
advHeading = oncomingLane.orientation[projectPt]

# Spawn the adversarial car in the oncoming lane, facing the ego vehicle
AdvAgent = Car at projectPt,
    with heading advHeading,
    with regionContainedIn None,
    with behavior AdvBehavior()