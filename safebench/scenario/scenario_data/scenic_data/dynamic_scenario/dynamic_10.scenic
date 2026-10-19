'''The ego vehicle is attempting to change lanes to avoid a slow-moving leading vehicle; the adversarial car in the target lane suddenly merges into the ego vehicle's original lane, blocking the ego vehicle from returning to its initial position.'''
Town = 'Town03'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    do FollowLaneBehavior(target_speed=globalParameters.OPT_ADV_SPEED) until (
        distance to self < globalParameters.OPT_ADV_DISTANCE and
        len(network.laneSectionAt(self).adjacentLanes) != 0 )
    # Identify the lane to switch into
    weaveLaneSec = network.laneSectionAt(self).adjacentLanes[0]
    # Execute the lane change
    do LaneChangeBehavior(laneSectionToSwitch=weaveLaneSec, target_speed=globalParameters.OPT_ADV_SPEED)

param OPT_ADV_SPEED = Range(5, 10)
param OPT_ADV_DISTANCE = Range(0, 20)
# Identifying lane sections that have both a left and a right lane (multi-lane road)
laneSecsWithBothSides = []
for lane in network.lanes:
    for laneSec in lane.sections:
        if laneSec._laneToLeft is not None and laneSec._laneToRight is not None:
            laneSecsWithBothSides.append(laneSec)

# Selecting a random lane section from identified sections for the ego vehicle
egoLaneSec = Uniform(*laneSecsWithBothSides)
egoSpawnPt = OrientedPoint in egoLaneSec.centerline

# Ego vehicle setup
ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
# Parameters for the adversarial agent's position relative to the ego vehicle
param OPT_GEO_Y_DISTANCE = Range(0, 10)  # Slightly ahead or alongside
param OPT_GEO_X_DISTANCE = Range(-2, 2)  # Lateral offset within the target lane

# Identify the target lane (the lane the ego is moving into)
# Assuming the ego is attempting a lane change to the left based on typical scenarios, 
# but we need to identify the specific lane. 
# In Scenic/CARLA, we often look at the lane to the left or right depending on the maneuver.
# Let's assume the target lane is the one to the left of the ego's current lane for a left lane change.
# If the description implies a general "target lane", we usually pick the adjacent lane in the direction of the maneuver.
# Here, we'll assume a left lane change as it's common, but the logic can be adapted.
advLane = network.laneSectionAt(ego)._laneToLeft.lane

# Calculate the spawn point in the target lane
# We project a point from the ego's position onto the target lane's centerline
IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE
projectPt = Vector(*advLane.centerline.project(IntSpawnPt.position).coords[0])
advHeading = advLane.orientation[projectPt]

# Spawn the Adversarial Agent in the target lane
AdvAgent = Car at projectPt,
    with heading advHeading,
    with regionContainedIn None,
    with behavior AdvBehavior()