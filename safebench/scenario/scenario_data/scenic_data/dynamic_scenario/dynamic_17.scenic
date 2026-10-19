'''The ego encounters a parked car blocking its lane and must use the opposite lane to bypass the vehicle when an oncoming pedestrian enters the lane without warning and suddenly stop, necessitating the ego to brake sharply or steer to avoid hitting the pedestrian.'''
Town = 'Town01'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    do CrossingBehavior(ego, globalParameters.OPT_ADV_SPEED, globalParameters.OPT_ADV_DISTANCE) until (distance from self to egoTrajectory) < globalParameters.OPT_STOP_DISTANCE
    while True:
        take SetWalkingSpeedAction(0)

param OPT_ADV_SPEED = Range(1, 5)
param OPT_ADV_DISTANCE = Range(0, 15)
param OPT_STOP_DISTANCE = Range(0, 1)
# Collecting lane sections that have a left lane (opposite traffic direction) and no right lane (single forward road)
laneSecsWithLeftLane = []
for lane in network.lanes:
    for laneSec in lane.sections:
        if laneSec._laneToLeft is not None and laneSec._laneToRight is None:
            if laneSec._laneToLeft.isForward != laneSec.isForward:
                laneSecsWithLeftLane.append(laneSec)

# Selecting a random lane section that matches the criteria
egoLaneSec = Uniform(*laneSecsWithLeftLane)
egoSpawnPt = OrientedPoint in egoLaneSec.centerline

# Ego vehicle setup
ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
# Setup the parked car (blocker) to force the ego vehicle into the opposite lane
param OPT_BLOCKER_DISTANCE = Range(10, 30)
param OPT_BLOCKER_SPEED = 0
BlockerSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_BLOCKER_DISTANCE
Blocker = Car at BlockerSpawnPt,
    with behavior FollowLaneBehavior(target_speed=globalParameters.OPT_BLOCKER_SPEED)

# Identify the opposite lane (left lane relative to ego's current path if ego is bypassing to the left, 
# but typically "opposite lane" implies the lane on the other side of the center line. 
# Assuming standard right-hand traffic and ego bypassing a right-side blocker, the opposite lane is to the left.
# However, the description says "into the opposite lane (the lane the ego is currently using to bypass the parked car)".
# This implies the ego has moved into the opposite lane. The pedestrian spawns in that same lane, in front of ego.

param OPT_GEO_Y_DISTANCE = Range(0, 10)
# The ego is in the opposite lane. We need to find the lane the ego is currently in.
# Since the ego is bypassing, it's likely in the lane to the left of its original lane.
# Let's assume the ego's current lane is the one to the left of the original lane.
# But to be robust, we can try to get the lane the ego is currently in.
# In Scenic, `ego` is an object. We can get its lane.
currentLane = network.laneAt(ego)

IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE
projectPt = Vector(*currentLane.centerline.project(IntSpawnPt.position).coords[0])
advHeading = currentLane.orientation[projectPt]

# Spawn the Adversarial Pedestrian
AdvAgent = Pedestrian at projectPt,
    with heading advHeading,
    with regionContainedIn None,
    with behavior AdvBehavior()