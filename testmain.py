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
apiKey = os.environ["NESSIE_API_KEY"]
apiai_url = "https://api.api.ai/v1/query"
apiai_querystring = {"v": "20150910"}
#Setting Google authorization credentials -  Read env data
credentials_dgf = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
registered_users = {"+919840610434": "Vijay",
                   "+914444461324": "Vijay"}

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
    	payload = {'event': {'name': 'welcome', 
			     'data': {'user_name': caller_name}
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
    
	# Welcome prompt played to callers during office hours
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

#####
##### Process Twilio ASR: Text to Intent analysis
#####
@app.route('/process_speech', methods=['GET', 'POST'])
def process_speech():
	cli = request.values.get('From')
	call_id = request.values.get('CallSid')
	twilio_asr_language = request.values.get('twilio_asr_language', 'en-IN')
	apiai_language = request.values.get('apiai_language', 'en')
	prior_text = request.values.get('prior_text', 'Prior text missing')
	input_text = request.values.get('SpeechResult', '')
	confidence = float(request.values.get('Confidence', 0.0))
	hostname = request.url_root
	print "Twilio Speech to Text: " + input_text + " Confidence: " + str(confidence)
    
	# Check for blank between digits and swapping the value if it has PII data
    	if re.search(r'\b\d{1,16}\b', input_text):
        	input_text = re.sub('(?<=\d) (?=\d)', '', input_text)
        	input_text1 = swap(input_text)
        	input_text = re.sub(r'\b\d{1,16}\b', input_text1, input_text)
        	print "Changed input: " + input_text
    	else:
        	print "Unchanged input: " + input_text
    	sys.stdout.flush()
    	resp = VoiceResponse()
	
    	if (confidence >= 0.0):

        	# Step 1: Call Dialogflow for intent analysis
        	intent_name, output_text = apiai_text_to_intent(apiai_client_access_key, input_text, call_id, apiai_language)

        	# Step 2: Speech input processing by Twilio
		values = {'prior_text': output_text}
        	qs2 = urllib.urlencode(values)
        	action_url = '/process_speech?' + qs2
        	gather = Gather(input="speech", hints=hints, language=twilio_asr_language, speechTimeout="auto", action=action_url, method="POST")
        	values = {"text": output_text}
		qs1 = urllib.urlencode(values)
		print 'In-progress: Before Google tts'
		gather.play(hostname + 'goog_text2speech?' + qs1)
		print 'In progress: After Google tts'
		resp.append(gather)
		
		# Transfer to agent for lost card
    		if intent_name == 'lost_card':
			resp.dial('+919840610434')
			resp.redirect('/process_close')
			
		# Transfer to agent for disputed transactions
    		if intent_name == 'transaction_dispute':
			resp.dial('+917338856833')
			resp.redirect('/process_close')
			
		# If gather is missing (no speech input), redirect to process incomplete speech via Dialogflow
		values = {'prior_text': output_text, 
			  'twilio_asr_language': twilio_asr_language, 
			  'apiai_language': apiai_language, 
			  'SpeechResult': '', 
			  'Confidence': 0.0
			 }
		qs3 = urllib.urlencode(values)
		action_url = '/process_speech?' + qs3
		resp.redirect(action_url)
    	
	# When confidence of speech recogniton is not enough, replay the previous conversation
	else:
		output_text = prior_text
        	values = {"prior_text": output_text}
		qs2 = urllib.urlencode(values)
		action_url = "/process_speech?" + qs2
		gather = Gather(input="speech", hints=hints, language=twilio_asr_language, speechTimeout="auto", action=action_url, method="POST")
		values = {"text": output_text}
		qs1 = urllib.urlencode(values)
		print 'Before Google tts'
		gather.play(hostname + 'goog_text2speech?' + qs1)
		print 'After Google tts read'
		resp.append(gather)
		values = {"prior_text": output_text}
		qs2 = urllib.urlencode(values)
		action_url = "/process_speech?" + qs2
		resp.redirect(action_url)
	print str(resp)
	return str(resp)

@app.route('/process_close', methods=['GET', 'POST'])
def process_close():
	print 'in process_close'

#####
##### Google Dialogflow - Intent identification from text
#####
#@app.route('/apiai_text_to_intent', methods=['GET', 'POST'])
def apiai_text_to_intent(apiapi_client_access_key, input_text, user_id, language):
	headers = {'authorization': "Bearer " + apiapi_client_access_key, 
		   'content-type': "application/json"
		  }
    	payload = {'query': input_text, 
		   'lang': language, 
		   'sessionId': user_id
		  }
    	response = requests.request("POST", url=apiai_url, data=json.dumps(payload), headers=headers, params=apiai_querystring)
    	output = json.loads(response.text)
    	print json.dumps(output, indent=2)
	
	try:
		intent_name = output['result']['metadata']['intentName']
	except:
		intent_name= ""
    	try:
        	output_text = output['result']['fulfillment']['speech']
    	except:
        	output_text = ""
    	
	return intent_name, output_text

#####
##### Reversing Values
#####
def swap(text):
    	actual = re.findall(r'\b\d{1,16}\b', text)
    	actvalue = actual[0]
    	text = actvalue[::-1]
    	print "Swap function result: " + text
    	return text

#####
##### Dialogflow fulfillment webhook
#####
@app.route('/webhook', methods=['POST'])
def webhook():
    	req = request.get_json(silent=True, force=True)
    	print 'Request:'
    	print json.dumps(req, indent=4)
    	res = processRequest(req)
    	res = json.dumps(res, indent=4)
    	r = make_response(res)
    	r.headers['Content-Type'] = 'application/json'
    	return r

def processRequest(req):
	lang = req.get('lang')
    	result = req.get('result')
    	metadata = result.get('metadata')
    	intentname = metadata.get('intentName')
    	parameters = result.get('parameters')
    	actionname = parameters.get('action')
    	accounttype = parameters.get('type')
    	accno = parameters.get('accnum')
    	print "Sent account Number is: " + str(accno)
    	payeeacc = parameters.get('transaccnum')
   	payeeaccounttype = parameters.get('transtype')
    	transamount = parameters.get('amount')
    	phoneNo = parameters.get('phonenumber')

   	# Get Balance Amount for account from account id
    	if intentname == 'Account_Balance':
        	accnumb = str(accno)
        	accountnumber = swap(accnumb)
        	print 'Account number:' + accountnumber
		if accounttype == 'spaargeld':
			accounttype = 'Savings'
		if accounttype == 'controleren':
			accounttype = 'Checking'
		if accounttype == 'kredietkaart':
			accounttype = 'Credit card'
        	Balance = getBalance(accountnumber, accounttype)
		if lang == 'nl':
			speech = 'Uw ' + accounttype + ' accountsaldo is ' \
			+ Balance + ' dollars. Kan ik je nog ergens anders mee helpen? U kunt uw laatste aankoop of laatste overdracht controleren of gewoon ophangen.'
		else:
			speech = 'Your ' + accounttype + ' account balance is ' \
			+ Balance + ' dollars. Is there anything else I can help you with today? You can check for your last purchase or last transfer or just hangup.'
        
   	 # Get Last transfer for account from account id
    	if intentname == 'Last_transfer':
        	accnumb = str(accno)
        	accountnumber = swap(accnumb)
        	print 'Account number:' + accountnumber
		if accounttype == 'spaargeld':
			accounttype = 'Savings'
		if accounttype == 'controleren':
			accounttype = 'Checking'
		if accounttype == 'kredietkaart':
			accounttype = 'Credit card'
        	lasttransfer = getLasttransfer(accountnumber, accounttype)
        	Amount = lasttransfer[0][u'amount']
		Transferamount = str(Amount)
        	date = lasttransfer[0][u'transaction_date']
        	Transferdate = str(date)
		if lang == 'nl':
			speech = 'De laatste overboeking die u deed, was op ' + Transferdate \
			+ ' voor ' + Transferamount + ' dollars. Kan ik je nog ergens anders mee helpen? U kunt uw saldo of de laatste overdracht controleren of gewoon ophangen'
		else:
			speech = 'The last transfer you made was for ' + Transferamount \
			+ ' dollars on ' + Transferdate + '.Is there anything else I can help you with today? You can check for your balance or last transfer or just hangup.'
        
    	# Get Last purchase for account from account id    
    	if intentname == 'Last_purchase':
        	accnumb = str(accno)
        	accountnumber = swap(accnumb)
        	print 'Account number:' + accountnumber
		if accounttype == 'spaargeld':
			accounttype = 'Savings'
		if accounttype == 'controleren':
			accounttype = 'Checking'
		if accounttype == 'kredietkaart':
			accounttype = 'Credit card'
        	lastpurchase = getLastpurchase(accountnumber, accounttype)
        	Amount = lastpurchase[0][u'amount']
        	Purchaseamount = str(Amount)
        	date = lastpurchase[0][u'purchase_date']
        	Purchasedate = str(date)
		if lang == 'nl':
			speech = 'De laatste aankoop die u deed, was op ' + Purchasedate \
			+ ' voor ' + Purchaseamount + ' dollars. Kan ik je nog ergens anders mee helpen? U kunt uw saldo of de laatste overdracht controleren of gewoon ophangen'
		else:
			speech = 'The last purchase you made was for ' + Purchaseamount \
			+ ' dollars on ' + Purchasedate + '.Is there anything else I can help you with today? You can check for your balance or last purchase or just hangup.'
   
    	# Transfer funds through account id
    	if intentname == 'Transfer_funds':
        	accnumb = str(accno)
        	accountnumber = swap(accnumb)
        	print 'Account number:' + accountnumber
        	payeeaccnumb = str(payeeacc)
        	payeeaccountnumber = swap(payeeaccnumb)
        	print 'Payee Account number:' + payeeaccountnumber
        	xferamount = str(transamount)
        	transferamount = swap(xferamount)
        	print 'Transfer amount:' + transferamount
        	result = createTransfer(accountnumber, accounttype, payeeaccountnumber, payeeaccounttype, transferamount)
        	responsecode = result[u'code']
        	transId = result[u'objectCreated'][u'_id']
        	if responsecode == 201:
            		speech = 'Your transfer request is successful. Your transaction id is ' + transId
        	else:
            		speech = 'Your transfer is not successful'
		
	# Report Lost card
	# Transfer to agent when user reports lost card
	if intentname == 'lost_card':
		speech = 'My colleague from the Customer Service Team will help you with your lost card report.'
		
	# Report bogus transactions
	# Transfer to agent when user reports transaction dispute
	if intentname == 'transaction_dispute':
		speech = 'My colleague from the Customer Service Team will help you with your transaction related issue.'
			
	# Handle Default Fallback Intent
	if intentname == 'Default Fallback Intent':
		speech = 'I not sure I quite understand. Apologies. I’m new here at ABN and still in training and learning about all our product lines, maybe if you could tell me the general reason for your call today like Account Balance or Last purchase'

	return {'speech': speech, 'source': 'apiai-account-sample'}
   	return res
    
#Helper function for Balance
def getBalance(accountnumber, accounttype):
    	with open('details.json') as json_file:
        	details = json.load(json_file)
        	print apiKey, accountnumber
        	accountId = details[accountnumber][accounttype]
        	print accountId
        	url = 'http://api.reimaginebanking.com/accounts/{}?key={}'.format(accountId, apiKey)
        	print url
        	response = requests.get(url, headers={'content-type': 'application/json'})
        	result = response.json()
        	accountbalance = result[u'balance']
        	Balance = str(accountbalance)
        	return Balance

#Helper function for Last Transfer
def getLasttransfer(accountnumber, accounttype):
	with open('details.json') as json_file:
        	details = json.load(json_file)
        	print apiKey, accountnumber
        	accountId = details[accountnumber][accounttype]
        	print accountId
        	url = 'http://api.reimaginebanking.com/accounts/{}/transfers?type=payer&key={}'.format(accountId, apiKey)
        	response = requests.get(url, headers={'content-type': 'application/json'})
        	lasttransfer = response.json()
        	return lasttransfer

#Helper function for Last Purchase
def getLastpurchase(accountnumber, accounttype):
    	with open('details.json') as json_file:
        	details = json.load(json_file)
        	print apiKey, accountnumber
        	accountId = details[accountnumber][accounttype]
        	print accountId
        	url = 'http://api.reimaginebanking.com/accounts/{}/purchases?key={}'.format(accountId, apiKey)
        	response = requests.get(url, headers={'content-type': 'application/json'})
        	lastpurchase = response.json()
        	return lastpurchase
    
#Helper function for Transfer funds
def createTransfer(accountnumber, accounttype, payeeaccountnumber, payeeaccounttype, transferamount):
    	with open('details.json') as json_file:
        	details = json.load(json_file)
        	dateObject = datetime.date.today()
        	dateString = dateObject.strftime('%Y-%m-%d')
        	payeraccountId = details[accountnumber][accounttype]
        	payeeaccountId = details[payeeaccountnumber][payeeaccounttype]
        	print payeeaccountId, payeraccountId
        	url = 'http://api.reimaginebanking.com/accounts/{}/transfers?key={}'.format(payeraccountId, apiKey)
        	payload = { 
			'medium': 'balance',
           		'payee_id': payeeaccountId, 
			'amount': float(transferamount), 
			'transaction_date': dateString, 
			'description': 'Personal'
		}
        	response = requests.post(url, data=json.dumps(payload), headers={'content-type': 'application/json'})
        	result = response.json()
        	print result
        	return result

#####
##### Google Cloud Text to speech for Speech Synthesis
##### This function calls Google TTS and then streams out the output media in mp3 format
#####
@app.route('/goog_text2speech', methods=['GET', 'POST'])
def goog_text2speech():
	text = request.args.get('text', "Oh No! There seems to be something wrong with my ram. Can you try calling back a little later after i talk to my friends in IT.")
	
	# Pre-process the text 
	#if len(text) == 0:
		#text = "We are experiencing technical difficulties at the moment. Please call back later."
	
	# Adding space between numbers for better synthesis
	#if re.search(r'\b\d{1,16}\b', text):
		#text = re.sub('(?<=\d)(?=\d)', ' ', text)
		#print "Changed input: " + text
	
	# Setting profile id
	effects_profile_id = 'telephony-class-application'
	
	#Generate Google TTS Credentials
	service_account_info = json.loads(credentials_dgf)
	credentials = service_account.Credentials.from_service_account_info(service_account_info)
		    
	# Create Google Text-To-Speech client
    	client = texttospeech.TextToSpeechClient(credentials=credentials)
	
	#Pass the text to be synthesized by Google Text-To-Speech
	input_text = texttospeech.types.SynthesisInput(text=text)
		
	#Set the Google Text-To-Speech voice parameters
    	voice = texttospeech.types.VoiceSelectionParams(language_code='en-AU', name='en-AU-Wavenet-B', ssml_gender=texttospeech.enums.SsmlVoiceGender.MALE)

	#Set Google Text-To-Speech audio configuration parameters
    	audio_config = texttospeech.types.AudioConfig(audio_encoding=texttospeech.enums.AudioEncoding.MP3, effects_profile_id=[effects_profile_id])

	# Request speech synthesis from Google Text-To-Speech
    	response = client.synthesize_speech(input_text, voice, audio_config)
	
	# Write the output to a temp file
	with open('output.mp3', 'wb') as out:
		out.write(response.audio_content)
		print('Audio content written to file "output.mp3"')
	
	if response.audio_content:
		# Read the audio stream from the response
		def generate():
			print 'inside google tts generate method'
			with open('output.mp3', 'rb') as dmp3:
				data = dmp3.read(1024)
				while data:
					yield data
					data = dmp3.read(1024)
			print 'generate complete for google tts'
		return Response(generate(), mimetype="audio/mpeg")
    	else:
		# If The response didn't contain audio data, exit gracefully
		print("Could not stream audio")
        	return "Error"
    
if __name__ == '__main__':
	app.run(host='0.0.0.0', debug = True)
