'''The ego vehicle is changing to the right lane; the adversarial car is driving parallel to the ego and blocking its path.'''
Town = 'Town03'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    while True:
        take SetVelocityAction(*ego.velocity)
        take SetSteerAction(0)  # Maintain straight path to block ego's lane
# Identifying straight lane sections with a right lane
laneSecsWithRightLane = []
for lane in network.lanes:
    for laneSec in lane.sections:
        if laneSec._laneToRight is not None and laneSec.isStraight:
            laneSecsWithRightLane.append(laneSec)

# Selecting a random lane section from identified sections for the ego vehicle
egoLaneSec = Uniform(*laneSecsWithRightLane)
egoSpawnPt = OrientedPoint in egoLaneSec.centerline

# Ego vehicle setup
ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
# Parameters for the adversarial agent's position relative to the ego vehicle
param OPT_GEO_Y_DISTANCE = Range(0, 20)  # Distance ahead/behind along the road direction
param OPT_GEO_X_DISTANCE = Range(0, 5)   # Lateral offset to ensure it is in the right lane

# Identify the right lane relative to the ego vehicle
advLane = network.laneSectionAt(ego)._laneToRight.lane

# Create an intermediate point along the road direction from the ego spawn point
IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE

# Project this point onto the centerline of the right lane to get the exact spawn position
projectPt = Vector(*advLane.centerline.project(IntSpawnPt.position).coords[0])
advHeading = advLane.orientation[projectPt]

# Spawn the adversarial car in the right lane, parallel to the ego vehicle
AdvAgent = Car at projectPt,
    with heading advHeading,
    with regionContainedIn None,
    with behavior AdvBehavior()