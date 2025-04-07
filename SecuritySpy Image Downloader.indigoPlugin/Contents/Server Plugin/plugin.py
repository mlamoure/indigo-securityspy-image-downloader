import os
import datetime
import time
import requests
import shutil
from PIL import Image
from distutils.version import LooseVersion
from requests.auth import HTTPDigestAuth
from requests.auth import HTTPBasicAuth

try:
    import indigo
except ImportError:
    pass

DEFAULT_UPDATE_FREQUENCY = 24 # frequency of update check
REQUEST_TIMEOUT = 30
################################################################################
class Plugin(indigo.PluginBase):
	########################################
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		self.debug = pluginPrefs.get("debug", False)
		self.securityspy_ip = pluginPrefs.get("ip", None)
		self.securityspy_port = pluginPrefs.get("port", None)
		self.securityspy_login = pluginPrefs.get("login", None)
		self.securityspy_pass = pluginPrefs.get("password", None)
		self.use_ssl = pluginPrefs.get("ssl", None)
		self.ss_auth_type = "basic" if self.securityspy_login else None

		self.last_update_check = None
		self.plugin_version = pluginVersion

		self.update_url()
		self.debug_log("Plugin initialized.")

	########################################
	def on_startup(self):
		self.debug_log("Plugin startup called")
		self.check_for_new_version()
		self.check_for_updates()

	def check_for_updates(self):
		self.check_for_new_version()

	def updateURL(self):
		self.configured = (self.securityspy_ip is not None) and (self.securityspy_port is not None)

		if self.use_ssl:
			self.securityspy_url = "https://" +  self.securityspy_ip + ":" + self.securityspy_port
		else:
			self.securityspy_url = "http://" + self.securityspy_ip + ":" + self.securityspy_port

	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		if not userCancelled:
			self.debug = valuesDict["debug"]
			self.securityspy_ip = valuesDict["ip"]
			self.securityspy_port = valuesDict["port"]
			self.securityspy_login = valuesDict["login"]
			self.securityspy_pass = valuesDict["password"]
			self.use_ssl = valuesDict["ssl"]

			self.ss_auth_type = None

			if len(self.securityspy_login) > 0: 
				self.ss_auth_type = "basic"

			self.updateURL()

	def check_for_new_version(self):
		plugin_id = self.pluginId
		self.last_update_check = datetime.datetime.now()

		# Fetch version info from Indigo plugin store
		current_version_url = "https://api.indigodomo.com/api/v2/pluginstore/plugin-version-info.json?pluginId={}".format(plugin_id)
		store_detail_url = "https://www.indigodomo.com/pluginstore/{}/"

		try:
			reply = requests.get(current_version_url, timeout=5)
			reply.raise_for_status()
			reply_dict = reply.json()
			plugin_dict = reply_dict["plugins"][0]
			latest_release = plugin_dict["latestRelease"]
			# Check for newer release
			if isinstance(latest_release, dict) and LooseVersion(latest_release["number"]) > LooseVersion(self.plugin_version):
				self.logger.info(
					"A new version of the plugin (v{}) is available at: {}".format(
						latest_release["number"],
						store_detail_url.format(plugin_dict["id"])
					)
				)
		except Exception as exc:
			self.logger.error(str(exc))

	def on_shutdown(self):
		self.debug_log("Plugin shutdown called")

	# helper functions
	def prepare_text_value(self, input_string):

		if strInput is None:
			return strInput
		else:
			strInput = strInput.strip()

			strInput = self.substitute(strInput)

			#fix issue with special characters
			strInput = strInput.encode('utf8')

			return strInput

	def runConcurrentThread(self):
		self.logger.debug("Starting concurrent tread")

		self.sleep(1)
		
		try:
			while True:
				self.sleep(int(DEFAULT_UPDATE_FREQUENCY + 1))

				if self.lastUpdateCheck < datetime.datetime.now()-datetime.timedelta(hours=DEFAULT_UPDATE_FREQUENCY):
					self.version_check()

		except self.StopThread:
			self.logger.debug("Received StopThread")

	def getImage(self, url, save, log = True, devId = None, auth_type = None, login = None, password = None):		
		try:
			save = save.decode("utf-8")

		except (UnicodeDecodeError, AttributeError):
			pass

		### Log
		if log or self.debug:
			if not devId is None:
				indigo.server.log("fetched image from '" + indigo.devices[devId].name + "' and saving it to: '" + str(save) + "' ")
			else:
				indigo.server.log("fetched image: " + str(url) + " and saving it to: '" + str(save)  + "'")

			self.debugLog("fetched image URL: " + str(url))

		try:
			if auth_type == None:
				r = requests.get(url, stream=True, timeout=100, verify=False)
			elif auth_type == "basic":
				r = requests.get(url, stream=True, timeout=100, verify=False, auth=HTTPBasicAuth(login, password))
			elif auth_type == "digest":
				r = requests.get(url, stream=True, timeout=100, verify=False, auth=HTTPDigestAuth(login, password))
			
			if r.status_code == 200:
				with open(save, 'wb') as f:
					r.raw.decode_content = True
					shutil.copyfileobj(r.raw, f)
			else:			
				self.logger.error("   error fetching image.  Status code: " + str(r.status_code))
				del r
				return False

			del r
#			self.logger.debug("   completed")
			return True
		except requests.exceptions.Timeout:
			self.logger.error("   the request timed out.")
			return False
		except Exception as e:
			self.logger.error("   error fetching image. error: " + str(e))
			return False

	def stitchImages(self, images):
		result_height = 0
		result_width = 0
		for image in images:
			(width, height) = image.size

			result_height = result_height + height

			if width > result_width:
				result_width = width

		result = Image.new('RGB', (result_width, result_height))

		curHeight = 0
		for image in images:
			(width, height) = image.size
			result.paste(im=image, box=(0, curHeight))
			curHeight = curHeight + height

		return result

	def stitchImageAction(self, pluginAction, dev):
		if not self.configured:
			return False

		start_time = time.time()

		try:
			if pluginAction.props["useVariable"]:
				destinationFile = indigo.variables[int(pluginAction.props["destinationVariable"])].value
			else:
				destinationFile = self.prepareTextValue(pluginAction.props["destination"])
		except:
			destinationFile = self.prepareTextValue(pluginAction.props["destination"])

		if not os.path.exists(os.path.dirname(destinationFile)):
			self.debug_log("Path does not exist: " + os.path.dirname(destinationFile))
			return False

		tempDirectory = os.path.dirname(destinationFile)
		images = []

		for i in range(1, 11):
			if "cam" + str(i) not in pluginAction.props or pluginAction.props["cam" + str(i)] == "-1" or pluginAction.props["cam" + str(i)] == "":
				self.debugLog("skipping camera")
				continue

			camera_devId = None
			for camera in [s for s in indigo.devices.iter(filter="org.cynic.indigo.securityspy.camera") if s.enabled]:
				cameranum = camera.address[camera.address.find("(")+1:camera.address.find(")")]

				if cameranum == pluginAction.props["cam" + str(i)]:
					camera_devId = camera.id
					camera_name = camera.name
					break

			image_url = self.securityspy_url + "/++image?cameraNum=" + pluginAction.props["cam" + str(i)]

			image_file = tempDirectory + "/temp" + str(i) + ".jpg"
			if not self.getImage(image_url, image_file, log = True, devId = camera_devId, auth_type = self.ss_auth_type, login = self.securityspy_login, password = self.securityspy_pass):
				self.debugLog("error obtaining image for camera '" + camera_name + "', skipping")
				image_url = None
			else:
				image = Image.open(image_file)

				try:
					if "imageSize" in pluginAction.props and int(pluginAction.props["imageSize"]):
						indigo.server.log("resized '" + camera_name + "' camera image to max width of " + pluginAction.props["imageSize"] + "px")
						size = int(pluginAction.props["imageSize"]), 100000
						image.thumbnail(size)
				except:
					pass

				images.append(image)

		result = self.stitchImages(images)
		result.save(destinationFile)

		end_time = time.time()
		total_time = round(end_time - start_time, 2)

		file_size = os.path.getsize(destinationFile) >> 20
		file_size_str = str(file_size) + " MB"

#		if file_size == 0:
		file_size = os.path.getsize(destinationFile) >> 10
		file_size_str = str(file_size) + " KB"

		indigo.server.log("stitched " + str(len(images)) + " camera images and saved to: " + destinationFile + " (" + file_size_str +").  Total time to create: " + str(total_time) + " seconds.")

		for i in range(1, 7):
			image_file = tempDirectory + "/temp" + str(i) + ".jpg"

			try:
				os.remove(image_file)
				self.debugLog("deleting file " + image_file)
			except:
				pass

	def CameraListGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
		FilterListUI = []

		for camera in [s for s in indigo.devices.iter(filter="org.cynic.indigo.securityspy.camera") if s.enabled]:
			cameraname = camera.name
			cameranum = camera.address[camera.address.find("(")+1:camera.address.find(")")]

			FilterListUI.append((cameranum, cameraname))

		if len(FilterListUI) == 0:
			FilterListUI.append((0, "Camera 0"))
			FilterListUI.append((1, "Camera 1"))
			FilterListUI.append((2, "Camera 2"))
			FilterListUI.append((3, "Camera 3"))
			FilterListUI.append((4, "Camera 4"))
			FilterListUI.append((5, "Camera 5"))
			FilterListUI.append((6, "Camera 6"))
			FilterListUI.append((7, "Camera 7"))
			FilterListUI.append((8, "Camera 8"))
			FilterListUI.append((9, "Camera 9"))
			FilterListUI.append((10, "Camera 10"))
			FilterListUI.append((11, "Camera 11"))
			FilterListUI.append((12, "Camera 12"))
			FilterListUI.append((13, "Camera 13"))
			FilterListUI.append((14, "Camera 14"))
			FilterListUI.append((15, "Camera 15"))

		FilterListUI.append(("-1", "none"))

		return FilterListUI

	def downloadImageAction(self, pluginAction, dev):

		###########
		### Validation
		###########
		if not self.configured:
			return False

		start_time = time.time()

		###########
		### Variable Preparation
		###########

		if "hidelog" in pluginAction.props:
			hide_log = pluginAction.props["hidelog"]
		else:
			hide_log = False

		# Destination File
		try:
			if pluginAction.props["useVariable"]:
				destinationFile = indigo.variables[int(pluginAction.props["destinationVariable"])].value
			else:
				destinationFile = self.prepareTextValue(pluginAction.props["destination"])
		except:
			destinationFile = self.prepareTextValue(pluginAction.props["destination"])
		
		try:
			destinationFile = destinationFile.decode("utf-8")
		except (UnicodeDecodeError, AttributeError):
			pass

		### VALIDATE: Check if the Destimation File Path exists
		if not os.path.exists(os.path.dirname(destinationFile)):
			self.logger.error("path does not exist: " + os.path.dirname(destinationFile))
			return False

		### Get the image URL for SecuritySpy Cameras
		camera_devId = None
		if pluginAction.props["type"] == "securityspy":
			for camera in [s for s in indigo.devices.iter(filter="org.cynic.indigo.securityspy.camera") if s.enabled]:
				cameranum = camera.address[camera.address.find("(")+1:camera.address.find(")")]

				if cameranum == pluginAction.props["cam1"]:
					camera_devId = camera.id
					camera_name = camera.name
					break

			image_url = self.securityspy_url + "/++image?cameraNum=" + pluginAction.props["cam1"]
		else:
			image_url = self.prepareTextValue(pluginAction.props["url"])

		## Python3 added the need to do this.
		try:
			image_url = image_url.decode("utf-8")
		except (UnicodeDecodeError, AttributeError):
			pass

		### Default the image size to the source
		imageSize = -1

		try:
			if "imageSize" in pluginAction.props and len(pluginAction.props["imageSize"]) > 0 and int(pluginAction.props["imageSize"]):
				imageSize = int(pluginAction.props["imageSize"])
		except:
			self.logger.error("error with the resize, must be integer.  Continuing without resizing.")

		### SET THE Auth properties for the URL
		getImage_login = self.securityspy_login
		getImage_password = self.securityspy_pass
		if pluginAction.props["type"] == "urlType":
			if "useAuth" not in pluginAction.props or pluginAction.props["useAuth"] == "none":
				getImage_auth = None
			else:
				getImage_auth = pluginAction.props["useAuth"]
				getImage_login = pluginAction.props["login"]
				getImage_password = pluginAction.props["password"]
		elif pluginAction.props["type"] == "securityspy":
				getImage_auth = self.ss_auth_type

		# END VARIABLE PREP

		###########
		### EXECUTION
		###########

		#### HANDLE SINGLE Downloads -- NON GIF.  Applies to both SecuritySpy and URL
		if "gif" not in pluginAction.props or not pluginAction.props["gif"]:
			tempDirectory = os.path.dirname(destinationFile)

			try:
				tempDirectory = tempDirectory.decode("utf-8")
			except (UnicodeDecodeError, AttributeError):
				pass

			if imageSize != -1:
				saveLocation = tempDirectory + "/temp_forResize.jpg"
			else:
				saveLocation = destinationFile

			try:
				self.getImage(image_url, saveLocation, log = not hide_log, devId = camera_devId, auth_type = getImage_auth, login = getImage_login, password = getImage_password)
			except:
				indigo.server.log("error fetching the image, not proceeding with resizing")
				return

			if imageSize != -1:
				image = Image.open(saveLocation)
				size = imageSize, 100000
				image.thumbnail(size)
				image.save(destinationFile)
				self.debugLog("deleting file " + saveLocation)
				os.remove(saveLocation)

			if not hide_log and pluginAction.props["type"] == "securityspy":
				indigo.server.log("fetched image from '" + camera_name + "', resized, and saved it to: " + destinationFile)
			elif not hide_log:
				indigo.server.log("fetched images from '" + image_url + "', resized, and saved it to: " + destinationFile)

		########################
		#### HANDLE ANIMATED GIF
		########################
		elif pluginAction.props["gif"]:
			quality = 60

			if os.path.splitext(destinationFile)[1] != ".gif":
				destinationFile = os.path.splitext(destinationFile)[0] + '.gif'

			tempDirectory = os.path.dirname(destinationFile)
			filenames = []
			i = 0

			try:
				total_gif_time = int(pluginAction.props["gifTime"])
			except:
				total_gif_time = 4

			while i * 2.0 <= total_gif_time:
				if i != 0:
					end_time = time.time()
					total_time = round(end_time - start_time, 2)
					sleep_time = (2*i) - total_time
					self.debugLog("time since start: " + str(total_time) + " seconds; sleeping for: " + str(sleep_time) + " seconds; total time for next frame grab: " + str(total_time + sleep_time) + " seconds.")
					time.sleep(sleep_time)
				
				tempFile = tempDirectory + "/temp_forGif" + str(i) + ".jpg"

				self.getImage(image_url, tempFile, log = not hide_log, devId = camera_devId, auth_type = getImage_auth, login = getImage_login, password = getImage_password)

				im = Image.open(tempFile)

				if imageSize != -1:
					size = imageSize, 100000
					im.thumbnail(size)

#					tempFile = os.path.splitext(tempFile)[0] + '.png'
				im.save(tempFile, 'JPEG', quality=quality)

				filenames.append(tempFile)
				i = i + 1

			end_time = time.time()
			total_time = round(end_time - start_time, 2)
			self.debugLog("Capture complete, time since start: " + str(total_time))

			# Open all the frames
			images = []
			for n in filenames:
				frame = Image.open(n)
				images.append(frame)
				self.debugLog("deleting file " + n)
				os.remove(n)

			# Save the frames as an animated GIF
			images[0].save(destinationFile,
						   save_all=True,
						   append_images=images[1:],
						   duration=300,
						   loop=0, quality=quality)

			file_size = os.path.getsize(destinationFile) >> 10
			file_size_str = str(file_size) + " KB"

			end_time = time.time()
			total_time = round(end_time - start_time, 2)
	
			if not hide_log and pluginAction.props["type"] == "securityspy":
				indigo.server.log("fetched images from '" + camera_name + "', created a animated gif (" + str(total_gif_time) + " seconds, " + str(i) + " frames), saved to: " + destinationFile + " (" + file_size_str +").  Total time to create: " + str(total_time) + " seconds.")
			elif not hide_log:
				indigo.server.log("fetched images from '" + image_url + "', created a animated gif (" + str(total_gif_time) + " seconds, " + str(i) + " frames), saved to: " + destinationFile + " (" + file_size_str +").  Total time to create: " + str(total_time) + " seconds.")

		### END Animated GIF
