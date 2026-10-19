'''The ego attempts an unprotected left turn at an intersection while yielding to an oncoming car when the oncoming car's suddenly brakes, necessitating the ego to rapidly reassess the situation and adjust its turn.'''
Town = 'Town05'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    while (distance to self) > 60:
        wait  # The adversarial vehicle waits until it is within a significant range to impact the ego's maneuver.
    do FollowTrajectoryBehavior(globalParameters.OPT_ADV_SPEED, advTrajectory) until (distance to self) < globalParameters.OPT_BRAKE_DISTANCE
    # Once within a critical distance of the intersection, the adversarial vehicle initiates a sudden braking maneuver.
    while True:
        take SetBrakeAction(globalParameters.OPT_BRAKE)  # Continues to apply brakes to simulate an emergency or unexpected stop.

param OPT_ADV_SPEED = Range(5, 15)  # The speed at which the adversarial vehicle approaches the intersection.
param OPT_BRAKE_DISTANCE = Range(0, 4)  # The critical distance at which the adversarial vehicle begins its sudden stop.
param OPT_BRAKE = Range(0, 1)  # The intensity of the braking action, potentially simulating an abrupt or gentle stop.

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