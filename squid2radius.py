#!/usr/bin/env python

import sys
import argparse
import time
import re
from subprocess import call
import pyrad.packet
from pyrad.client import Client
from pyrad.dictionary import Dictionary


parser = argparse.ArgumentParser(description='Analyze squid log by user ' \
                                             'and upload result to RADIUS ' \
                                             'server.')
parser.add_argument('logfile_path', help='logfile to analyze')
parser.add_argument('radius_server')
parser.add_argument('radius_secret')
parser.add_argument('-p', '--radius-acct-port', default='1813')
parser.add_argument('--radius-nasid', default='squid')
parser.add_argument('--squid-path', default='/usr/sbin/squid')
parser.add_argument('--exclude-pattern', help='do not send to server if ' \
                                              'username contains this regexp',
                                         default='')
parser.add_argument('--no-rotation', help='do not rotate squid log files',
                                     action='store_true')
args = parser.parse_args()


logfile = open(args.logfile_path)
print logfile

sys.stdout.write("Analyzing")
sum_bytes = {}
for i, line in enumerate(logfile):
  if i % 1000 == 0: sys.stdout.write('.'); sys.stdout.flush()
  
  # http://wiki.squid-cache.org/Features/LogFormat
  _, _, _, _, num_bytes, _, _, rfc931, _, _ = line.split()[:10]
  
  if rfc931 == '-': continue
  
  try:
    sum_bytes[rfc931] = sum_bytes[rfc931] + int(num_bytes)
  except KeyError:
    sum_bytes[rfc931] = int(num_bytes)


print "\nSetting up RADIUS server..."
srv = Client(server=args.radius_server, secret=args.radius_secret,
             dict=Dictionary(sys.path[0] + "/dictionary"))


if args.exclude_pattern:
  print "Exclusion check has been enabled."
  exclude_pattern = re.compile(args.exclude_pattern)


print "Sending..."
for username, total_bytes in sum_bytes.iteritems():
  sys.stdout.write(username + ' ' + str(total_bytes))
  sys.stdout.write('.')
  sys.stdout.flush()
  
  if args.exclude_pattern and exclude_pattern.search(username):
    sys.stdout.write("..skipped!\n")
    sys.stdout.flush()
    continue

  session_id = str(time.time())

  req = srv.CreateAcctPacket()
  req['User-Name'] = username
  req['NAS-Identifier'] = args.radius_nasid
  req['Acct-Session-Id'] = session_id
  req['Acct-Status-Type'] = 1  # Start

  reply = srv.SendPacket(req)
  if not reply.code == pyrad.packet.AccountingResponse:
    raise Exception("mysterious RADIUS server response to Start packet")

  sys.stdout.write('.')
  sys.stdout.flush()

  req = srv.CreateAcctPacket()
  req['User-Name'] = username
  req['NAS-Identifier'] = args.radius_nasid
  req['Acct-Session-Id'] = session_id
  req['Acct-Status-Type'] = 2  # Stop
  req['Acct-Output-Octets'] = total_bytes

  reply = srv.SendPacket(req)
  if not reply.code == pyrad.packet.AccountingResponse:
    raise Exception("mysterious RADIUS server response to Stop packet")

  sys.stdout.write(".\n")
  sys.stdout.flush()

if not args.no_rotation:
  print "\nRotating squid log..."
  call([args.squid_path, "-k", "rotate"])

