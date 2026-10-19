'''The ego vehicle is driving on a straight road; the adversarial pedestrian is hidden behind a vending machine on the right front, and abruptly dashes out onto the road, and stops directly in the path of the ego.'''
Town = 'Town03'
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
# Identifying straight lanes
straightLanes = []
for lane in network.lanes:
    if lane.isStraight:
        straightLanes.append(lane)

# Selecting a random straight lane for the ego vehicle
egoLane = Uniform(*straightLanes)
egoSpawnPt = OrientedPoint in egoLane.centerline

# Ego vehicle setup
ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
param OPT_GEO_BLOCKER_X_DISTANCE = Range(2, 8)
param OPT_GEO_BLOCKER_Y_DISTANCE = Range(15, 50)
param OPT_GEO_X_DISTANCE = Range(-2, 2)
param OPT_GEO_Y_DISTANCE = Range(2, 6)

RightFrontSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_BLOCKER_Y_DISTANCE
Blocker = VendingMachine right of RightFrontSpawnPt by globalParameters.OPT_GEO_BLOCKER_X_DISTANCE,
    with heading RightFrontSpawnPt.heading,
    with regionContainedIn None

SHIFT = globalParameters.OPT_GEO_X_DISTANCE @ globalParameters.OPT_GEO_Y_DISTANCE
AdvAgent = Pedestrian at Blocker offset along RightFrontSpawnPt.heading by SHIFT,
    with heading RightFrontSpawnPt.heading + 90 deg,
    with regionContainedIn None,
    with behavior AdvBehavior()