'''The ego vehicle is maintaining a constant speed; the adversarial car, comes from the right, blocks multiple lanes by driving extremely slowly, forcing the ego vehicle to change lanes.'''
Town = 'Town03'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    while (distance to self) > 60:
        wait  # The adversarial car waits until it is within impactful range.
    
    # Drive extremely slowly to block lanes and force lane changes.
    while True:
        take SetSpeedAction(globalParameters.OPT_SLOW_SPEED)

param OPT_SLOW_SPEED = Range(0, 2)  # The extremely slow speed that the adversarial car adopts to block lanes.
# Identifying lane sections that are part of a straight road with multiple lanes
# A straight road segment is typically represented by a lane section where the lane is straight
# and has adjacent lanes (left or right) moving in the same direction, implying multiple lanes.
laneSecsWithMultipleLanes = []
for lane in network.lanes:
    for laneSec in lane.sections:
        # Check if the lane section is straight (no curvature)
        isStraight = laneSec._lane is not None and laneSec._lane.isStraight
        # Check if there is at least one adjacent lane (left or right) moving in the same direction
        hasLeftLane = laneSec._laneToLeft is not None and laneSec._laneToLeft.isForward == laneSec.isForward
        hasRightLane = laneSec._laneToRight is not None and laneSec._laneToRight.isForward == laneSec.isForward
        
        if isStraight and (hasLeftLane or hasRightLane):
            laneSecsWithMultipleLanes.append(laneSec)

# Selecting a random lane section from identified sections for the ego vehicle
egoLaneSec = Uniform(*laneSecsWithMultipleLanes)
egoSpawnPt = OrientedPoint in egoLaneSec.centerline

# Ego vehicle setup
ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
# Identifying the adjacent lane to the right for the Adversarial Agent and setting its spawn point
param OPT_GEO_Y_DISTANCE = Range(0, 30)
advLane = network.laneSectionAt(ego)._laneToRight.lane
IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE
projectPt = Vector(*advLane.centerline.project(IntSpawnPt.position).coords[0])
advHeading = advLane.orientation[projectPt]

# Spawn the Adversarial Agent
AdvAgent = Car at projectPt,
    with heading advHeading,
    with regionContainedIn None,
    with behavior AdvBehavior()