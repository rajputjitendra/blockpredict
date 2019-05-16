import sys
import os
from datetime import timezone, timedelta, datetime as dt
import time
import dateutil.parser
import argparse
import pickle

import numpy as np
import matplotlib as mpl
#mpl.use('Agg') #for use without X server. Disable if needed
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

sys.path.insert(0, os.path.realpath('neural'))
from neural_network import NeuralNetwork
from custom_deep_network import CustomDeepNetwork
from basic_lstm_network import BasicLSTMNetwork
from conv2d_network import Conv2DNetwork
from conv3d_network import Conv3DNetwork

globalModels = [Conv2DNetwork(), Conv3DNetwork(), BasicLSTMNetwork()]

modelExtension = '.h5'
historyExtension = '.pickle'
graphExtension = '.svg'

def loadDataset(filename):
	with open(filename, 'rb') as f:
		return pickle.load(f)

def randomizeDataset(dataset, labels, dates):
	permutation = np.random.permutation(labels.shape[0])
	shuffled_dataset = dataset[permutation,:,:]
	shuffled_labels = labels[permutation]
	shuffled_dates = dates[permutation]
	return shuffled_dataset, shuffled_labels, shuffled_dates

def run(datasetFile, models, modelArgs={}, saveModel=None, loadModel=None, quiet=False, shuffle=True, trim=False, train=True):
	#load the datasets
	print("Loading dataset %s." % datasetFile)
	rawDataset = loadDataset(datasetFile)

	dataset = {}
	labels = {}
	dates = {}
	normalization = {}

	history = {}

	for i, kind in enumerate(['warm', 'train', 'test']):
		targetLen = len(rawDataset[i]['dataset'])

		if trim:
			if not quiet:
				print("Trimming %s dataset." % kind)
			targetLen -= targetLen % modelArgs['batch']

		dataset[kind] = rawDataset[i]['dataset'][:targetLen]

		labels[kind] = rawDataset[i]['labels'][:targetLen]

		dates[kind] = rawDataset[i]['dates'][:targetLen]

		normalization[kind] = rawDataset[i]['normalization']


	selectedModels = []

	if shuffle:
		print("Shuffling train dataset.")
		dataset['train'], labels['train'], dates['train'] = randomizeDataset(dataset['train'], labels['train'], dates['train'])

	if models != None:
		for model in globalModels:
			if model.name.lower() in models: #case insensitive
				selectedModels.append(model)
	else: selectedModels = globalModels

	if not quiet:
		print("Starting to train and evaluate the following networks: ", [net.name for net in selectedModels])

	for model in selectedModels:
		if loadModel:
			model.load(loadModel)
		if train:
			history[model.name] = model.train(dataset, labels, modelArgs, targetNormalization = normalization['train'])

			print(history[model.name])

			if saveModel is not None:
				model.save(saveModel+modelExtension)
				with open(saveModel+historyExtension, 'wb') as f:
					data = {}
					data['history'] = history[model.name]
					data['model'] = model.name
					data['dataset'] = datasetFile
					data['args'] = modelArgs

					pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)

	if not quiet:
		print("Trained the networks.")

	if not quiet:
		print("Running prediction on test dataset.")

	for model in selectedModels:
		predictions = []
		actuals = []
		datesList = []

		for setType in ['train', 'test']:
			res = NeuralNetwork.reverse_target_normalization(model.predict(dataset[setType]), normalization[setType])
			actual = NeuralNetwork.reverse_target_normalization(labels[setType], normalization[setType])

			p = dates[setType].argsort()
			predictions.append(res[p])
			actuals.append(actual[p])
			datesList.append(dates[setType][p])

		filename = None

		if saveModel is not None:
			filename = saveModel+graphExtension
		hist = history.get(model.name, None)
		drawAccuracyGraph(model.name, datesList, predictions, actuals, history=hist, filename=filename)
	print("Used dataset %s and arguments %s" % (datasetFile, modelArgs))

def simulateTrading(prediction, actual, startBalance):
	balance = startBalance #start with 100 of the stable currency

	crypto = False #what currency are we holding? crypto (predicted) or the stable one.

	lastPriceBoughtCrypto = 1

	timesTraded = 0

	for i, curr in enumerate(actual):
		if i >= len(prediction) - 1: break

		pred = prediction[i+1]

		if not crypto and pred > curr: #if the crypto price will raise and we're not on crypto
			crypto = True
			balance /= curr
			lastPriceBoughtCrypto = curr
			timesTraded += 1
		elif crypto and curr < pred: #if the crypto price will fall and we are holding crypto
			crypto = False
			balance *= curr
			timesTraded += 1

	if crypto:
		balance *= lastPriceBoughtCrypto #if we have finished with balance on crypto, revert last time we bought it.
		crypto = False

	return (balance, timesTraded)

def drawAccuracyGraph(name, dates, predictions, actuals, history=None, filename=None):
	fig = plt.figure(figsize=(16*2, 9*2))

	if type(predictions) != list:
		predictions = [predictions]
	if type(actuals) != list:
		actuals = [actuals]
	if type(dates) != list:
		dates = [dates]

	rows = 0
	
	for actual in actuals:
		rows += actual.shape[1]
	
	if history is not None:
		cols = len(history.keys())
		rows += 1
	else:
		cols = 1
	gs = GridSpec(rows, cols)

	currRow = 0

	for prediction, actual, date in zip(predictions, actuals, dates):
		for i in range(actual.shape[1]):
			plt.subplot(gs[currRow, :])
			currRow += 1

			plt.plot(date, actual[:, i], label='Target %d' % i, color='blue')
			if prediction is not None:
				plt.plot(date, prediction[:, i], label='Predicted %d' % i, color='red')
			plt.x = date
			plt.legend(loc='upper left')
	if history is not None:
		for i, measure in enumerate(list(history.keys())):
			plt.subplot(gs[currRow, i])

			plt.plot(history[measure], label=measure)
			plt.legend(loc='upper left')

	fig.suptitle('Performance of %s' % name)
	plt.tight_layout()

	if filename is None:
		plt.show()
	else:
		plt.savefig(filename)
		print("Saved accuracy graph at %s." % filename)

def init():
	parser = argparse.ArgumentParser(description="Module that loads given datasets and trains and evaluates one or more neural network models on that.")
	parser.add_argument('dataset', type=str, help="The filepath to the dataset/s.")
	parser.add_argument('--models', type=str, help="A list of the models that are going to be trained and evaluated. Default is all available.")
	parser.add_argument('--args', type=str, help="A list of arguments to be passed on to the models. In the format key1=value1,key2=value2.1;value2.2")
	parser.add_argument('--quiet', dest='quiet', action="store_true", help="Do not plot graphs, but save them as images.")
	parser.set_defaults(quiet=False)
	parser.add_argument('--saveModel', type=str, help="Location to save the model architecture, weights, training history, evaluation scores and prediction graphs. DO NOT include file extension, just filename!")
	parser.add_argument('--loadModel', type=str, help="Location to to load a saved model architecture and weights. Include the file extension!")
	parser.add_argument('--shuffle', dest='shuffle', action="store_true", help="Shuffle the generated dataset and labels.")
	parser.set_defaults(shuffle=False)
	parser.add_argument('--trim-batch', dest='trim', action="store_true", help="Trim each dataset so that its length is divisible by the batch size.")
	parser.set_defaults(trim=False)
	parser.add_argument('--no-replace', dest='noReplace', action="store_true", help="If a model is already saved with the same filename, don't train and save the new model.")
	parser.set_defaults(noReplace=False)
	parser.add_argument('--no-train', dest='train', action="store_false", help="Do not train, only evaluathe the model.")
	parser.set_defaults(train=True)

	args, _ = parser.parse_known_args()

	if args.noReplace and args.saveModel is not None:
		if os.path.exists(args.saveModel+modelExtension):
			print("The file already exists and the 'no-replace' flag is used.")
			return #do not replace it

	givenModels = [x.lower() for x in args.models.split(',')] if args.models else None

	modelArgs = {}
	pairs = args.args.split(',') if args.args else []
	for pair in pairs:
		key, value = pair.split('=')

		try:
			value = float(value)
			if value == int(value):
				value = int(value)
		except ValueError:
			if ':' in value:
				value = [int(i) for i in value.split(':')]
			pass
		modelArgs[key] = value

	print("Processed model arguments", modelArgs)

	run(args.dataset, givenModels, modelArgs=modelArgs, quiet=args.quiet, saveModel=args.saveModel, loadModel=args.loadModel, shuffle=args.shuffle, trim=args.trim, train=args.train)

if __name__ == "__main__": #if this is the main file, parse the command args
	init()