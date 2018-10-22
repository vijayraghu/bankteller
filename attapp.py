# -*- coding: utf-8 -*-
import os
import sys
import urllib
import requests
import json
from flask import Flask, request, Response, make_response, jsonify, url_for
from contextlib import closing
# Twilio Helper Library
from twilio.twiml.voice_response import VoiceResponse, Gather, Say, Dial
import re
import datetime
# Google Text To Speech SDK
from google.oauth2 import service_account
from google.cloud import texttospeech_v1beta1 as texttospeech

# Declare global variables
apiai_client_access_key = os.environ["APIAPI_CLIENT_ACCESS_KEY"]
apiai_url = "https://api.api.ai/v1/query"
apiai_querystring = {"v": "20150910"}
#Setting Google authorization credentials -  Read env data
credentials_dgf = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')

# Setup hints for better speech recognition
hints = "1,2,3,4,5,6,7,8,9,0, 1 one first, 2 two second, 3 three third, 4 four fourth, 5 five fifth, 6 six sixth, 7 seven seventh, 8 eight eighth,9 nine ninth, 10 ten tenth, account acount akount, january, february, march, april, may, june, july, august, september, october, november, december, savings, checking, credit card, transfer, fund, funds, purchase, transaction, dispute, bogus"

app = Flask(__name__)

@app.route('/start', methods=['GET','POST'])
def start():
	caller_phone_number = request.values.get('From')
	call_id = request.values.get('CallSid')
	twilio_asr_language = request.values.get('twilio_asr_language', 'en-IN')
	apiai_language = request.values.get('apiai_language', 'en')
	hostname = request.url_root
	caller_name = registered_users.get(caller_phone_number, ' ')
    	hostname = request.url_root

    	# Initialize Dialogflow agent
    	headers = {'authorization': 'Bearer ' + apiai_client_access_key, 
		   'content-type': 'application/json'
		  }
    	payload = {'event': {'name': 'welcome'
			    }, 
		   'lang': apiai_language, 'sessionId': call_id
		  }
    
    	response = requests.request("POST", url=apiai_url, data=json.dumps(payload), headers=headers, params=apiai_querystring)
    	print response.text
    	output = json.loads(response.text)
    	output_text = output['result']['fulfillment']['speech']
    	output_text = output_text.decode('utf-8')
    	resp = VoiceResponse()

    	# Prepare for next set of user Speech
    	values = {'prior_text': output_text}
    	qs = urllib.urlencode(values)
    	action_url = '/process_speech?' + qs
    	gather = Gather(input="speech", hints=hints, language=twilio_asr_language, speechTimeout="auto", action=action_url, method="POST")
    
	# Play welcome prompt
	values = {"text": output_text}
	qs = urllib.urlencode(values)
	print 'In start: before Google TTS'
	gather.play(hostname + 'goog_text2speech?' + qs)
	print 'In start: after Google TTS'
	resp.append(gather)

	# If user input is missing after welcome prompt (no speech input), redirect to collect speech input again
	values = {'prior_text': output_text, 
		  'twilio_asr_language': twilio_asr_language, 
		  'apiai_language': apiai_language, 
		  'SpeechResult': '', 
		  'Confidence': 0.0
		 }
	qs = urllib.urlencode(values)
	action_url = '/process_speech?' + qs
	resp.redirect(action_url)
	print str(resp)
	return str(resp)
