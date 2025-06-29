# Setup Guide for Lego Star Wars: The Complete Saga in Archipelago

Work-in-progress.

## Required Software
- PC Release of Lego Star Wars: The Complete Saga
  - Both the Steam version and GOG version are supported.
  - Running the 'steamless' executable is not expected to work currently, but is untested and should be supported in the
future.
  - The retail PC release is not expected to work currently, unless it is identical to the GOG version.
- Archipelago
- Windows Operating System
  - The client uses the pymem library, to read from/write to the game's memory, which only supports Windows.

## Optional Software
- [Lego Star Wars: The Complete Saga Archipelago Tracker](https://github.com/Mysteryem/TCS_AP_PopTracker/releases/latest), 
for use with [PopTracker](https://github.com/black-sliver/PopTracker/releases)
- [Dxwnd](https://dxwnd.org/) to play in a window instead of fullscreen
  - Works better with the GOG version.
  - The Steam version can sometimes crash when starting when run through Dxwnd, but it is stable once it starts 

## Connecting to the Archipelago server
When connecting to a multiworld for the first time, a new game should be started. Save slots are bound to the first
multiworld and slot name they were connected to. To resume playing a multiworld at a later time, the same save slot that
initially connected to that multiworld should be loaded. 

To connect to the multiworld server, run the **Lego Star Wars: The Complete Saga Client** from the Archipelago Launcher
and connect it to the Archipelago server. Lego Star Wars: The Complete Saga must be running before a connection can be
made.

The first time a save file connects to an Archipelago server, the slot name needs to be entered. After that, the slot
name will be set into the save data and read automatically from the save file by the client when connecting.