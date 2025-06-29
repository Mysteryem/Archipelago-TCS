# Lego Star Wars: The Complete Saga

Work-in-progress.

## What does randomization do to this game?

Story Mode is skipped for episode levels, which are always played in Free Play.

To unlock a level, all Story Mode characters for that level must be acquired and the corresponding Episode Unlock item
must be received.

The player always start with Episode 1 unlocked, as well as Qui-gon Jinn, Obi-wan Kenobi and TC-14 unlocked.

## What items and locations get randomized?

### Items
Characters, Extras (that require a Power Brick) and Minikits are in the item pool.

Episode Unlock items are added to the item pool.

Score Multiplier Extras are replaced with Progressive Score Multiplier items that unlock more Score Multiplier Extras
the more Progressive Score Multipliers are acquired.

Progressive Bonus Level items are added to the pool, that are required to unlock more Bonus Levels.

Purple Stud items are added to the item pool to fill out the rest of the item pool.

### Locations

Making purchases from the Characters or Extras shop are locations to check.
The Extras that can be purchased without collecting a Power Brick are not currently location checks.

Completing an Episode level in Free Play is a location to check.

Completing the True Jedi for a level is a location to check.

Every 1-10 number of Minikits collected in a level is a check.

## What other changes are made to the game?

Purchases in the Characters shop and Extras shop will not award their vanilla Characters/Extras.

Slots in the Characters shop that would normally unlock upon completing Story mode in every level now unlock once all
Episodes have been unlocked.

Bonus levels require Progressive Bonus Level items to unlock, in addition to their Story mode characters for bonuses
with Story mode. The Gold Brick doors to each Bonus level will automatically build themselves once they are unlocked and
should not be built by the player.

- Bonus level 1 (Mos Espa Pod Race (Original)) requires 1 Progressive Bonus Level.
- Bonus level 2 requires 2 Progressive Bonus Level.
- etc.

## What does another world's item look like in Lego Star Wars: The Complete Saga?

All items display as they would in vanilla.

## When the player receives an item, what happens?

The item is immediately added to your unlocked Extras/Characters/Stud count. A text display in-game may show what the
received item was.

Studs are added to your total accumulated Studs rather than your in-level Studs, so the effect of receiving Studs is
not noticeable without returning to the Cantina. The received studs are multiplied by your maximum possible score
multiplier.

## Can I play offline?

No, a connection to the Archipelago server is required to receive items, even in a single-player multiworld.

If the connection to the Archipelago server is lost, it is possible to continue playing. Any checked locations while
disconnected will be sent once the connection is reestablished.

## Known Issues

### Logic

The logic is quite basic and has issues because all characters of a specific type are grouped together, e.g. Battle
Droid, Ewok and Stormtrooper are all considered 'Blaster' characters, despite Battle Droids and Ewoks not being able to
Grapple and Ewoks having a different projectile.

The intention is to completely overhaul the logic in the future, adding support for individual minikit logic, different
starting levels and different unlock requirements for levels.

There is currently no logic for expensive shop purchases, so purchasing Score x10 could be expected before any
Progressive Score Multiplier items have been received. Until there is logic for expensive shop purchases, if a
multiworld expects an unreasonable purchase, you can enter the cheat code in the shop for that character/extra to unlock
that character/extra without having to farm an unreasonable number of studs.

### In-game messages

Dying while a received item/checked location message is displayed will cause you to lose studs, but no studs will spawn
to be picked back up.

Collecting studs while an in-game message is displayed will play the sound for collecting Blue/Purple studs, but the
received value of the collected studs will be normal.

In some cases, the Double Score Zone background audio can start playing when in-game messages are displayed.

### Bonus levels/Indiana Jones Trailer

There is currently no way to prevent access to Bonus Levels/Indiana Jones Trailer without the logically required
Progressive Bonus Level items.

Bonus Level entrances will build themselves automatically when they are supposed to be unlocked, but there is no
indicator for the Indiana Jones Trailer becoming logically accessible.

### 'All Episodes' Character unlocks

Slots in the Characters shop that would normally unlock upon completing Story mode in every level now unlock once all
Episodes have been unlocked. There may be a small delay before the purchase will be allowed, and other slots in the shop
may appear to be unlocked while making the purchase.

### Purchasing already unlocked Characters/Extras

When attempting to purchase a Character/Extra that has already been unlocked, by receiving that Character/Extra from
Archipelago, there may be a small delay before the purchase will be allowed.

### Purple Studs

Receiving a Purple Stud item adds the studs directly to your save data, the stud counter visible in the Cantina.

Receiving a Purple Stud while in a level will not add it to your in-level stud count or contribute to True Jedi
progress.

Receiving a Purple Stud while under the effect of a Power Up, or while in a Double Score Zone will not double the
received studs.

### Cantina Episode door lights

If you are in the main room of the Cantina when you unlock your first level in an episode, the red lights above the
episode door won't change to green, but the door can still be entered normally. The lights will become green the next
time you enter the main room of the Cantina.