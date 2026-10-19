'''The ego vehicle is turning right at an intersection; the adversarial pedestrian on the left front suddenly crosses the road and stops in the middle of the intersection, blocking the ego vehicle's path.'''
Town = 'Town05'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    do CrossingBehavior(ego, globalParameters.OPT_ADV_SPEED, globalParameters.OPT_ADV_DISTANCE) until (distance from self to egoTrajectory) < globalParameters.OPT_STOP_DISTANCE
    while True:
        take SetWalkingSpeedAction(0)

param OPT_ADV_SPEED = Range(0, 5)
param OPT_ADV_DISTANCE = Range(0, 15)
param OPT_STOP_DISTANCE = Range(0, 1)
intersection = Uniform(*filter(lambda i: i.is4Way or i.is3Way, network.intersections))
egoManeuver = Uniform(*filter(lambda m: m.type is ManeuverType.RIGHT_TURN, intersection.maneuvers))
egoInitLane = egoManeuver.startLane
egoTrajectory = [egoInitLane, egoManeuver.connectingLane, egoManeuver.endLane]
egoSpawnPt = OrientedPoint in egoInitLane.centerline

ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
# Define hyperparameters for the adversarial agent's position relative to the ego vehicle
param OPT_GEO_X_DISTANCE = Range(-10, -2)  # Left side offset (negative X)
param OPT_GEO_Y_DISTANCE = Range(5, 20)    # Front offset (positive Y)

# Calculate the spawn point for the adversarial agent
# First, move forward along the road direction from the ego spawn point
FrontSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE

# Then, shift to the left by the specified X distance
AdvSpawnPt = OrientedPoint left of FrontSpawnPt by globalParameters.OPT_GEO_X_DISTANCE

# Spawn the adversarial agent at the calculated position
AdvAgent = Pedestrian at AdvSpawnPt,
    with heading AdvSpawnPt.heading,
    with regionContainedIn None,
    with behavior AdvBehavior()