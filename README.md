This plugin is a helper set of actions for users of SecuritySpy and Indigo.  It creates two actions for downloading images from SecuritySpy.

# Plugin Actions #
* Action 1: Simple download to the local mac (source can be SecuritySpy or a specified URL)
* Action 2: Download multiple images and stitch them together vertically

These are intended to be used in tandum with triggers to save local copies of your security camera to your Mac, typically so that they can be used again for a notification, such as with the Pushover plugin.

# Instructions #
Example use and setup:

* Step 1: Create variables for each of your cameras with the full path to a location to store a snapshot of that camera.  E.g.  outside_camera1_snapshot    /Users/bob/Documents/CameraImages/outside_camera1_snapshot.jpg
* Step 2: Copy the IDs for each of the variables
* Step 3: Create a "Download URL/SecuritySpy Image" Action or Action Group to download the camera image using this plugin.  Get the camera number for your cameras by using the web interface for SecuritySpy and looking for the "cameraNum" variable in the URL bar when viewing the desired camera.  -- UPDATE (v1.1): If using Cynical SecuritySpy plugin, your camera numbers and names will automatically be loaded for you.
* Step 4: In the action config, enter %%v:XXXXXX%% for the Destination location
* Step 5: Try it out.
* Step 6: Create pushover notifications with attachments using the same variable.
* Step 7: Create triggers for the actions created in previous steps.  For example: Motion detected outside when not home, download outside camera image, send pushover notification.