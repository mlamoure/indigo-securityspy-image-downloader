#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################

import indigo

import os
import sys
import datetime
import time
import requests
import urlparse
import shutil
from PIL import Image
from distutils.version import LooseVersion

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
		self.lastUpdateCheck = None

		self.updateURL()

	########################################
	def startup(self):
		self.debugLog(u"startup called")
		self.version_check()

	def checkForUpdates(self):
		self.version_check()

	def updateURL(self):
		self.configured = (self.securityspy_ip is not None) and (self.securityspy_port  is not None)

		if self.configured:
			if self.securityspy_login is not None:
				self.securityspy_url = "http://" + self.securityspy_login + ":" + self.securityspy_pass + "@" +  self.securityspy_ip + ":" + self.securityspy_port
			else:
				self.securityspy_url = "http://" + self.securityspy_ip + ":" + self.securityspy_port

	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		if not userCancelled:
			self.debug = valuesDict["debug"]
			self.securityspy_ip = valuesDict["ip"]
			self.securityspy_port = valuesDict["port"]
			self.securityspy_login = valuesDict["login"]
			self.securityspy_pass = valuesDict["password"]

			self.updateURL()

	def version_check(self):
		pluginId = self.pluginId
		self.lastUpdateCheck = datetime.datetime.now()		

		# Create some URLs we'll use later on
		current_version_url = "https://api.indigodomo.com/api/v2/pluginstore/plugin-version-info.json?pluginId={}".format(pluginId)
		store_detail_url = "https://www.indigodomo.com/pluginstore/{}/"
		try:
			# GET the url from the servers with a short timeout (avoids hanging the plugin)
			reply = requests.get(current_version_url, timeout=5)
			# This will raise an exception if the server returned an error
			reply.raise_for_status()
			# We now have a good reply so we get the json
			reply_dict = reply.json()
			plugin_dict = reply_dict["plugins"][0]
			# Make sure that the 'latestRelease' element is a dict (could be a string for built-in plugins).
			latest_release = plugin_dict["latestRelease"]
			if isinstance(latest_release, dict):
				# Compare the current version with the one returned in the reply dict
				if LooseVersion(latest_release["number"]) > LooseVersion(self.pluginVersion):
				# The release in the store is newer than the current version.
				# We'll do a couple of things: first, we'll just log it
				  self.logger.info(
					"A new version of the plugin (v{}) is available at: {}".format(
						latest_release["number"],
						store_detail_url.format(plugin_dict["id"])
					)
				)
		except Exception as exc:
			self.logger.error(unicode(exc))

	def shutdown(self):
		self.debugLog(u"shutdown called")

	# helper functions
	def prepareTextValue(self, strInput):

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

	def getImage(self, url, save, log = True):
		parsed = urlparse.urlparse(url)

		replaced = parsed._replace(netloc="{}:{}@{}".format(parsed.username, "<password removed from log>", parsed.hostname))

		if log:
			indigo.server.log("getting image: " + replaced.geturl() + " and saving it to: " + save)

		try:
			r = requests.get(url, stream=True, timeout=100)

			if r.status_code == 200:
				with open(save, 'wb') as f:
					r.raw.decode_content = True
					shutil.copyfileobj(r.raw, f)
			else:			
				self.logger.error("   error getting image.  Status code: " + str(r.status_code))
				del r
				return False

			del r
			self.logger.debug("   completed")
			return True
		except requests.exceptions.Timeout:
			self.logger.error("   the request timed out.")
		except Exception as e:
			self.logger.error("   error getting image. error: " + str(e))
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

		try:
			if pluginAction.props["useVariable"]:
				destinationFile = indigo.variables[pluginAction.props["destinationVariable"]].value
			else:
				destinationFile = self.prepareTextValue(pluginAction.props["destination"])
		except:
			destinationFile = self.prepareTextValue(pluginAction.props["destination"])

		if not os.path.exists(os.path.dirname(destinationFile)):
			self.debugLog("path does not exist: " + os.path.dirname(destinationFile))
			return False

		tempDirectory = os.path.dirname(destinationFile)
		images = []

		image1_url = self.securityspy_url + "/++image?cameraNum=" + pluginAction.props["cam1"]

		image1_file = tempDirectory + "/temp1.jpg"
		if not self.getImage(image1_url, image1_file):
			self.debugLog("error obtaining image 2, skipping")
			image1_url = None
		else:
			image = Image.open(image1_file)

			try:
				if "imageSize" in pluginAction.props and int(pluginAction.props["imageSize"]):
					indigo.server.log("resized camera 1 to max width of " + pluginAction.props["imageSize"])
					size = int(pluginAction.props["imageSize"]), 100000
					image.thumbnail(size, Image.ANTIALIAS)
			except:
				pass

			images.append(image)

		image2_url = None
		image3_url = None
		image4_url = None

		if pluginAction.props["cam2"] != "-1":
			image2_url = self.securityspy_url + "/++image?cameraNum=" + pluginAction.props["cam2"]

			image2_file = tempDirectory + "/temp2.jpg"
			if not self.getImage(image2_url, image2_file):
				self.debugLog("error obtaining image 2, skipping")
				image2_url = None
			else:
				image = Image.open(image2_file)

				try:
					if "imageSize" in pluginAction.props and int(pluginAction.props["imageSize"]):
						indigo.server.log("resized camera 2")
						size = int(pluginAction.props["imageSize"]), 100000
						image.thumbnail(size, Image.ANTIALIAS)
				except:
					pass

				images.append(image)

		if pluginAction.props["cam3"] != "-1":
			image3_url = self.securityspy_url + "/++image?cameraNum=" + pluginAction.props["cam3"]

			image3_file = tempDirectory + "/temp3.jpg"
			if not self.getImage(image3_url, image3_file):
				self.debugLog("error obtaining image 3, skipping")
				image3_url = None
			else:
				image = Image.open(image3_file)

				try:
					if "imageSize" in pluginAction.props and int(pluginAction.props["imageSize"]):
						indigo.server.log("resized camera 3")
						size = int(pluginAction.props["imageSize"]), 100000
						image.thumbnail(size, Image.ANTIALIAS)
				except:
					pass

				images.append(image)

		if pluginAction.props["cam4"] != "-1":
			image4_url = self.securityspy_url + "/++image?cameraNum=" + pluginAction.props["cam4"]

			image4_file = tempDirectory + "/temp4.jpg"
			if not self.getImage(image4_url, image4_file):
				self.debugLog("error obtaining image 4, skipping")
				image4_url = None
			else:
				image = Image.open(image4_file)

				try:
					if "imageSize" in pluginAction.props and int(pluginAction.props["imageSize"]):
						indigo.server.log("resized camera 4")
						size = int(pluginAction.props["imageSize"]), 100000
						image.thumbnail(size, Image.ANTIALIAS)
				except:
					pass

				images.append(image)

		result = self.stitchImages(images)
		result.save(destinationFile)

		try:
			if image2_url != None:
				os.remove(image1_file)
		except:
			pass

		try:
			if image2_url != None:
				os.remove(image2_file)
		except:
			pass

		try:
			if image3_url != None:
				os.remove(image3_file)
		except:
			pass

		try:
			if image4_url != None:
				os.remove(image4_file)
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

	def downloadImage(self, pluginAction, dev):
		if not self.configured:
			return False

		try:
			if pluginAction.props["useVariable"]:
				destinationFile = indigo.variables[pluginAction.props["destinationVariable"]].value
			else:
				destinationFile = self.prepareTextValue(pluginAction.props["destination"])
		except:
			destinationFile = self.prepareTextValue(pluginAction.props["destination"])

		if not os.path.exists(os.path.dirname(destinationFile)):
			self.logger.error("path does not exist: " + os.path.dirname(destinationFile))
			return False

		if pluginAction.props["type"] == "securityspy":
			image_url = self.securityspy_url + "/++image?cameraNum=" + pluginAction.props["cam1"]
		else:
			image_url = self.prepareTextValue(pluginAction.props["url"])

		imageSize = -1

		try:
			if "imageSize" in pluginAction.props and len(pluginAction.props["imageSize"]) > 0 and int(pluginAction.props["imageSize"]):
				imageSize = int(pluginAction.props["imageSize"])
		except:
			self.logger.error("error with the resize, must be integer.  Continuing without resizing.")

		try:
			if imageSize != -1:
				tempDirectory = os.path.dirname(destinationFile)
				tempFile = tempDirectory + "/temp_forResize.jpg"
				self.getImage(image_url, tempFile, True)
				image = Image.open(tempFile)
				size = imageSize, 100000
				image.thumbnail(size, Image.ANTIALIAS)
				image.save(destinationFile)
				os.remove(tempFile)
				indigo.server.log("obtained image, resized, and saved it to: " + destinationFile)
			else:
				self.getImage(image_url, destinationFile)
		except Exception as e:
			self.logger.error("error resizing the image: " + str(e))
			self.getImage(image_url, destinationFile)

