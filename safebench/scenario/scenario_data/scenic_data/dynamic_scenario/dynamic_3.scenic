'''The ego vehicle is driving on a straight road; the adversarial pedestrian appears from a driveway on the left and suddenly stop and walk diagonally.'''
Town = 'Town03'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    while (distance to self) > globalParameters.OPT_ADV_DISTANCE:
        wait
    # Suddenly stop
    take SetWalkingSpeedAction(0)
    wait globalParameters.OPT_STOP_DURATION
    # Walk diagonally
    direction = self.heading + globalParameters.OPT_ADV_DEGREE deg
    take SetWalkingDirectionAction(direction)
    take SetWalkingSpeedAction(globalParameters.OPT_ADV_SPEED)

param OPT_ADV_SPEED = Range(0, 5)
param OPT_ADV_DISTANCE = Range(0, 15)
param OPT_ADV_DEGREE = Range(-90, 90)
param OPT_STOP_DURATION = Range(1, 3)
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
param OPT_GEO_Y_DISTANCE = Range(10, 40)
param OPT_GEO_X_DISTANCE = Range(-15, -5)

IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE
AdvAgent = Pedestrian at IntSpawnPt offset left by globalParameters.OPT_GEO_X_DISTANCE,
    with heading IntSpawnPt.heading,
    with regionContainedIn None,
    with behavior AdvBehavior()