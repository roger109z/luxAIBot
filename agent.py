import math, sys
from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES, Position
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate
from lux.game_objects import City, Player

DIRECTIONS = Constants.DIRECTIONS
game_state = None
plannedMoves = []
projects = []
onProject = {}
debug = ""

#map from gamestate, width of map, height of map
#returns a list containing cell references with resources in them
def getResourceTiles(map):
    width = map.width
    height = map.height
    resourceTiles: list[Cell] = []
    for y in range(height):
        for x in range(width):
            cell = map.get_cell(x, y)
            if cell.has_resource():
                resourceTiles.append(cell)
    
    return resourceTiles


def canHarvest(resourceTile, player):
    if resourceTile.resource.type == Constants.RESOURCE_TYPES.COAL and not player.researched_coal(): return False
    if resourceTile.resource.type == Constants.RESOURCE_TYPES.URANIUM and not player.researched_uranium(): return False

    return True

def getNumType(resourceTile):
    types = {
        Constants.RESOURCE_TYPES.WOOD: 0,
        Constants.RESOURCE_TYPES.COAL: 1,
        Constants.RESOURCE_TYPES.URANIUM: 2
    }

    return types[resourceTile.resource.type]

def stepsUntilNight(step):
    cyclesDone = math.floor(step/45)
    
    thisStep = step - cyclesDone*45

    return 30 - thisStep

def findNearestResource(unitPos, resourceTiles, player):
    closest_dist = math.inf
    closest_resource_tile = None
    thisType = -1

    for resource_tile in resourceTiles:
        if not canHarvest(resource_tile, player): continue
        dist = resource_tile.pos.distance_to(unitPos)
        checkType = getNumType(resource_tile)
        if (dist < closest_dist or checkType > thisType) and not plannedMoves[resource_tile.pos.x][resource_tile.pos.y]:
            closest_dist = dist
            closest_resource_tile = resource_tile
            thisType = checkType
    
    return closest_resource_tile

def findNearestWorker(pos, units):
    closestDist = math.inf
    closestUnit = None
    if len(units) > 0:
        for unit in units:
            dist = unit.pos.distance_to(pos)
            if dist < closestDist:
                closestDist = dist
                closestUnit = unit

    return closestUnit

def findNearestCity(unit, cities):
    closestDist = math.inf
    closestCityTile = None
    if len(cities) > 0:
        for _, city in cities.items():
            for cityTile in city.citytiles:
                dist = cityTile.pos.distance_to(unit.pos)
                if dist < closestDist:
                    closestDist = dist
                    closestCityTile = cityTile

    return closestCityTile

def checkCanCreateUnit(player):
    totalCityTiles = 0;
    for k in player.cities:
        city = player.cities[k]
        totalCityTiles += len(city.citytiles)
    if len(player.units) < totalCityTiles:
        return True
    return False

def checkCanBuildCity(cities):
    for k in cities:
        city = cities[k]
        fuel = city.fuel
        requiredFuel = city.get_light_upkeep()
        if fuel < requiredFuel:
            return False
    
    return True

def locationChecked(checkedLocations, location):
    for locationToCheck in checkedLocations:
        if locationToCheck[0] == location[0] and locationToCheck[1] == location[1]:
            return True
    return False

def getCityCenter(city):
    posx, posy, total = (0, 0, 0)

    for cityTile in city:
        position = cityTile.pos
        posx += position.x
        posy += position.y
        total += 1
    
    return Position(int(posx/total), int(posy/total))
        

def getCityTilesWithFreeSpace(city, map):
    global debug

    tilesWithFreeSpace = []
    freeSpaces = []
    offsets = [[1, 0], [0, 1], [-1, 0], [0, -1]]
    for cityTile in city.citytiles:
        position = cityTile.pos
        found = False
        for offset in offsets:
            tileToCheck = [position.x + offset[0], position.y + offset[1]]
            if tileToCheck[0] > map.width-1 or tileToCheck[0] < 0 or tileToCheck[1] > map.height or tileToCheck[1] < 0: continue
            tile = map.get_cell(tileToCheck[0], tileToCheck[1])
            isProject = projects[tileToCheck[0]][tileToCheck[1]]
            if (not tile.has_resource()) and tile.citytile == None and (not isProject):
                if not found: 
                    tilesWithFreeSpace.append(cityTile)
                    found = True
                
                freeSpaces.append([tileToCheck[0], tileToCheck[1]])

                debug += f"Pos: {str(tileToCheck[0])}:: {str(tileToCheck[1])}:: has_resource: {str(tile.has_resource())} "
                

    
    return tilesWithFreeSpace, freeSpaces

def getSmallestCity(cities):
    smallestNum = math.inf
    smallest = None

    for k in cities:
        city = cities[k]
        if smallestNum > len(city.citytiles):
            smallestNum = len(city.citytiles)
            smallest = city
    
    return smallest

def findBestBuildLocation(player, map):
    distToResource = math.inf
    buildLocation = None

    city = getSmallestCity(player.cities)

    _, freeSpaces = getCityTilesWithFreeSpace(city, map)

    for pos in freeSpaces:
        thisPos = Position(pos[0], pos[1])
        resource = findNearestResource(thisPos, getResourceTiles(map), player)
        dist = resource.pos.distance_to(thisPos)
        if dist < distToResource:
            buildLocation = thisPos
            distToResource = dist

    return buildLocation

    


def cityAction(cityTile, canCreateUnit):
    if cityTile.can_act():
        if canCreateUnit:
            return cityTile.build_worker()
        else:
            return cityTile.research()
        
def findLowestOpen(nodes):
    lowest = math.inf
    lowestPos = None

    for k, j in nodes.items():
        if j[4] < lowest:
            lowest = j[4]
            lowestPos = k
        elif j[4] == lowest:
            if j[3] < nodes[lowestPos][3]:
                lowestPos = k

    return lowestPos

def getDirection(pos1, pos2, closedNodes, pos2ParentPos):
    current = pos2
    parent = pos2ParentPos
    while not parent.equals(pos1):
        current = parent
        parent = closedNodes[f'{parent.x},{parent.y}'][5]

    return pos1.direction_to(current)



def pathfind(pos1, pos2, team, map):

    global plannedMoves

    outMap = []

    for i in range(map.width):
        outMap.append([])
        for j in range(map.height):
            cell = map.get_cell(i, j)

            if cell.citytile != None:
                if cell.citytile.team != team:
                    outMap[i].append(False)
                else:
                    outMap[i].append(True)
            else:
                if plannedMoves[i][j]:
                    outMap[i].append(False)
                else:
                    outMap[i].append(True)

    #str(f'{x},{y}') = [x, y, g, h, f, parentPos]

    openNodes = {}
    closedNodes = {}

    openNodes[f'{pos1.x},{pos1.y}'] = [pos1.x, pos1.y, 0, pos2.distance_to(pos1), pos2.distance_to(pos1)]

    while len(openNodes) > 0:
        index = findLowestOpen(openNodes)
        current = openNodes.pop(index)
        closedNodes[f'{current[0]},{current[1]}'] = current

        if current[0] == pos2.x and current[1] == pos2.y: #path found
            #we need to add where we are moving to to plannedMoves

            dir = DIRECTIONS.CENTER
            
            try:
                dir = getDirection(pos1, pos2, closedNodes, current[5])
            except:
                pass

            futurePos = pos1.translate(dir, 1)
            plannedMoves[futurePos.x][futurePos.y] = True
            return dir
        
        offsets = [[1, 0], [0, 1], [-1, 0], [0, -1]]
        for offset in offsets:
            pos = Position(current[0]+offset[0], current[1]+offset[1])
            if pos.x > map.width-1 or pos.x < 0 or pos.y > map.height-1 or pos.y < 0:
                continue

            if not outMap[pos.x][pos.y] or f'{pos.x},{pos.y}' in closedNodes:
                continue

            gCost = pos1.distance_to(pos)
            hCost = pos2.distance_to(pos)
            fCost = gCost + hCost

            if (f'{pos.x},{pos.y}' in openNodes and openNodes[f'{pos.x},{pos.y}'][4] > fCost) or not f'{pos.x},{pos.y}' in openNodes:
                openNodes[f'{pos.x},{pos.y}'] = [pos.x, pos.y, gCost, hCost, fCost, Position(current[0], current[1])]
    
    plannedMoves[pos1.x][pos1.y] = True
    return DIRECTIONS.CENTER


    #g cost 

def unitAction(resourceTiles, unit, player, map, canBuildCity):

    global projects
    global onProject
    global plannedMoves

    if unit.get_cargo_space_left() > 0:
        # if the unit is a worker and we have space in cargo, lets find the nearest resource tile and try to mine it
        closestResourceTile = findNearestResource(unit.pos, resourceTiles, player)
        if closestResourceTile is not None:
            dir = pathfind(unit.pos, closestResourceTile.pos, player.team, map)
            return unit.move(dir)
    else:
        if canBuildCity:
            if unit.id in onProject:
                proj = onProject[unit.id]
                projx = proj['pos'].x
                projy = proj['pos'].y

                if unit.pos.x == projx and unit.pos.y == projy:
                    onProject.pop(unit.id)
                    projects[projx][projy] = False
                    return unit.build_city()
                else:
                    moveDir = pathfind(unit.pos, Position(projx, projy), -1, map)
                    return unit.move(moveDir)
            else:
                buildPos = findBestBuildLocation(player, map)
                if not buildPos: 
                    closestCityTile = findNearestCity(unit, player.cities)
                    if closestCityTile is not None:
                        moveDir = pathfind(unit.pos, closestCityTile.pos, player.team, map)
                        return unit.move(moveDir)
                onProject[unit.id] = {'pos': buildPos}
                projects[buildPos.x][buildPos.y] = True

                moveDir = pathfind(unit.pos, buildPos, -1, map)
                return unit.move(moveDir)
        else:
            # if unit is a worker and there is no cargo space left, and we have cities, lets return to them
        
            closestCityTile = findNearestCity(unit, player.cities)
            if closestCityTile is not None:
                moveDir = pathfind(unit.pos, closestCityTile.pos, player.team, map)
                return unit.move(moveDir)
    return False

def agent(observation, configuration):
    global game_state
    global projects
    global onProject
    global plannedMoves
    global debug

    ### Do not edit ###
    if observation["step"] == 0:
        game_state = Game()
        game_state._initialize(observation["updates"])
        game_state._update(observation["updates"][2:])
        game_state.id = observation.player
    else:
        game_state._update(observation["updates"])
    
    actions = []

    ### AI Code goes down here! ### 

    player = game_state.players[observation.player]
    opponent = game_state.players[(observation.player + 1) % 2]
    width, height = game_state.map.width, game_state.map.height

    if observation['step'] == 0:
        for i in range(width):
            projects.append([])
            for _ in range(height):
                projects[i].append(False)

    plannedMoves = []
    for i in range(width):
        plannedMoves.append([])
        for _ in range(height):
            plannedMoves[i].append(False)

    canBuildCity = checkCanBuildCity(player.cities) and stepsUntilNight(observation['step']) > 5


    resourceTiles = getResourceTiles(game_state.map)

    # we iterate over all our units and do something with them
    for unit in player.units:
        if unit.is_worker() and unit.can_act():
            action = unitAction(resourceTiles, unit, player, game_state.map, canBuildCity)
            if action:
                actions.append(action)
            
    for k in player.cities:
        city = player.cities[k]
        for cityTile in city.citytiles:
            action = cityAction(cityTile, checkCanCreateUnit(player))
            if action:
                actions.append(action)

    for i in onProject:
        cur = onProject[i]
        actions.append(annotate.circle(cur['pos'].x, cur['pos'].y))

    for i in debug:
        actions.append(annotate.text(0, 0, i))

    # you can add debug annotations using the functions in the annotate object
    # actions.append(annotate.circle(0, 0))
    
    return actions
