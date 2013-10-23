#!/usr/bin/env python

# httpp.py
# http proxy
# A python implementation for http proxy with multi threads
# Oct 23, 2013
# NOTE: ctrl-C may not able to kill the process timely as the main
# methods is waiting for other thread's join. setDaemon() could be
# used by each thread before start() to force the main to exit regardless
# of other threads - BUT this is not a graceful way to do the clean up!
# - daveti
# Oct 21, 2013
# daveti@cs.uoregon.edu
# http://davejingtian.org

import socket
import threading
import errno
import BaseHTTPServer
import StringIO

# Global configuration of httpp
serverIp = "128.223.4.21"
serverPort = 33333
serverListenMax = 1000
sockBuffLenMax = 10240
clientSockTimeout = 100 # seconds
httpDefaultPort = 80
workerIndex = 0 
workingThreads = []

# HTTP request class
class HTTPRequest(BaseHTTPServer.BaseHTTPRequestHandler):
	# Constructor(parser)
	def __init__(self, request_text):
		self.rfile = StringIO.StringIO(request_text)
		self.raw_requestline = self.rfile.readline()
		self.error_code = self.error_message = None
		self.parse_request()

	# Error code handling
	def send_error(self, code, message):
		self.error_code = code
		self.error_message = message

# Worker thread class
class Worker(threading.Thread):
	# Constructor
	def __init__(self, index, cSock, cIp, cPort):
		threading.Thread.__init__(self)
		self.index = index
		self.clientSock = cSock
		self.clientIp = cIp,
		self.clientPort = cPort
		# Set the time out for the client socket
		self.clientSock.settimeout(clientSockTimeout)

	# Create proxy socket
	def createProxySock(self, host):
		self.proxySock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.proxySock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.proxySock.settimeout(clientSockTimeout)
		self.proxySock.connect((host, httpDefaultPort))
		print("Worker[%d]: Connecting to host [%s:%d]" %(self.index, host, httpDefaultPort))

	# Main method of worker
	def run(self):
		print("Worker[%d]: Connecting with [%s:%d]" %(self.index, self.clientIp, self.clientPort))
		# Recv the http request
		while True:
			msg = ''
			try:
				while True:
					data = self.clientSock.recv(sockBuffLenMax)
					msg += data
					if len(data) < sockBuffLenMax:
						break
						
			except socket.timeout:
				print("Worker[%d]: Timeout for client [%s:%d]" %(self.index, self.clientIp, self.clientPort))
				break

			# Check if we should exit
			if len(msg) == 0:
				print("Worker[%d]: Socket connection broken for client [%s:%d]" %(self.index, self.clientIp, self.clientPort))
				break

			# Check if this is a valid http request
			request = HTTPRequest(msg)
			if request.error_code != None:
				print("Worker[%d]: Invalid HTTP request with error code [%d] - [%s] from client [%s:%d]" %(self.index, request.error_code, request.error_message, self.clientIp, self.clientPort))
				# May terminate the whole thread - but now, leave it
				continue

			# Get the target IP/Port from the request
			host = request.headers['host']
			print("Worker[%d]: Got HTTP request to host [%s]" %(self.index, host))

			# Create the proxy socket and forward the request to the host
			self.createProxySock(host)
			try: 
				sentLen = self.proxySock.send(msg)
				if sentLen != len(msg):
					print("Worker[%d]: Forward the HTTP request to host [%s] failed" %(self.index, host))
				else:
					print("Worker[%d]: Forward the HTTP request to host [%s]" %(self.index, host))

			except socket.error, e:
				if isinstance(e.args, tuple):
					print("Worker[%d]: Forward the HTTP request to host [%s] with errno [%d]" %(self.index, host, e[0]))
					if e[0] == errno.EPIPE:
						# remote peer disconnected
						print("Worker[%d]: Detected remote host [%d] disconnectted" %(self.index, host))
						break
				else:
					print("Worker[%d]: Forward the HTTP request to host [%s] with socket error [%s]" %(self.index, host, e))
					break

			# Recv from the host and forward the reply to the client
			while True:
				msg2 = ''
				try:
					while True:
						data2 = self.proxySock.recv(sockBuffLenMax)
						msg2 += data2
						if len(data2) < sockBuffLenMax:
							break

				except socket.timeout:
					print("Worker[%d]: Timeout for the host [%s]" %(self.index, host))
					break

				if len(msg2) == 0:
					print("Worker[%d]: Socket connection broken for the host [%s]" %(self.index, host))
					break

				# NOTE: no http pkg parsing right now - just forwarding
				print("Worker[%d]: Got HTTP reply from the host [%s]" %(self.index, host))
				try:
					sentLen = self.clientSock.send(msg2)
					if sentLen != len(msg2):
						print("Worker[%d]: Forward the HTTP reply to the client [%s:%d] failed" %(self.index, self.clientIp, self.clientPort))
					else:
						print("Worker[%d]: Forward HTTP reply to the client [%s:%d]" %(self.index, self.clientIp, self.clientPort))

				except socket.error, e:
					if isinstance(e.args, tuple):
						print("Worker[%d]: Forward the HTTP reply to client [%s:%d] with errno [%d]" %(self.index, self.clientIp, self.clientPort, e[0]))
						if e[0] == errno.EPIPE:
							# remote peer disconnected
							print("Worker[%d]: Detected remote client [%s:%d] disconnectted" %(self.index, self.clientIp, self.clientPort))
							break
					else:
						# As long as the remote socket is not closed, try out best (without break)
						print("Worker[%d]: Forward the HTTP reply to client [%s:%d] with socket error [%s]" %(self.index, self.clientIp, self.clientPort, e)) 

			# Done the reply forwarding
			# Waiting for the request from the client
			self.proxySock.close()

		self.clientSock.close()
		print("Worker[%d]: Done" %(self.index))


# Main method of httpp
if __name__ == "__main__":
	# Create the server socket
	serverSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	serverSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	serverSock.bind((serverIp, serverPort))

	# Do the damn job
	while True:
		serverSock.listen(serverListenMax)
		print("httpp: Listening on [%s:%d]" %(serverIp, serverPort))
		(clientSock, (clientIp, clientPort)) = serverSock.accept()
		# Create a new worker
		worker = Worker(workerIndex, clientSock, clientIp, clientPort)
		worker.start()
		workingThreads.append(worker)
		workerIndex += 1
	# Close the server socket
	serverSock.close()

	# Join all the worker - main has to wait for all the threads...
	for t in workingThreads:
		t.join()

