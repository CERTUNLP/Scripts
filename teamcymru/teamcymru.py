#!/bin/python3
#
# This file is part of the Kintun - Restful Vulnerability Scanner
#
# (c) CERT UNLP <support@cert.unlp.edu.ar>
#
# This source file is subject to the GPL v3.0 license that is bundled
# with this source code in the file LICENSE.
#
# Author: Mateo Durante <mdurante@cert.unlp.edu.ar>
#
from http.client import HTTPSConnection
from base64 import b64encode
import re, datetime, requests
from send_mail import MailLog
import sys, traceback
import config_teamcymru

send_external = False

ngen_url_staging_internal = config_teamcymru.NGEN["url_internal_staging"]
ngen_url_staging_external = config_teamcymru.NGEN["url_external_staging"]
ngen_url_prod_internal = config_teamcymru.NGEN["ngen_url_prod_internal"]
ngen_url_prod_external = config_teamcymru.NGEN["ngen_url_prod_external"]

user = config_teamcymru.TEAMCYMRU["user"]
password = config_teamcymru.TEAMCYMRU["password"]

maillog = MailLog(config_teamcymru.MAILLOG)

def process_file():
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    domain = "www.tcconsole.com"
    resource = '/export/{0}/malevolence.txt'.format(yesterday.strftime('%Y%m%d'))
    # This sets up the https connection
    c = HTTPSConnection(domain)
    # we need to base 64 encode it and then decode it to acsii as python 3 stores it as a byte string
    userAndPass = b64encode(("{0}:{1}".format(user,password)).encode('ascii')).decode("ascii")
    headers = { 'Authorization' : 'Basic %s' %  userAndPass }
    # then connect
    c.request('GET', resource, headers=headers)
    res = c.getresponse()
    if res.code == 404:
        raise Exception('404 en teamcymru. Posiblemente no hay nuevo contenido de feed.')
    # at this point you could check the status etc
    # this gets the page text
    data = res.read().decode('utf-8', errors='ignore').split('\n')
    #print(data)
    #original = "# timestamp\tip\tasn\told_category\tmalware\tgeoip\tcomment\taddtime\tcategory\trir\tcc\tloadindex\tdstip\tsrcport\tdstport"
    original = "# timestamp\tip_addr\tasn\tport\tproto\tconfidence\tcc\tnotes\tcategory\tfamily"
    new = data[0]
    if new != original:
        raise Exception('{0}\nOriginal: {1}\nNuevo: {2}'.format("El formato de la pagina es distinto al original",original,new))

    reports = data[1:-1]
    report_header = data[0]
    #print( reports)
    return report_header,[item.split('\t') for item in reports]

def isUNLP(ip):
    return ip[:7] == '163.10.'

def process_lines(header,lines):
    headers = {'Accept' : '*/*', 'Expect': '100-continue'}
    externals = []
    log_info = []
    error = False
    hosts = {}
    for line in lines:
        # Separo evidencias por hosts
        l = '\t'.join(line)
        if line[1] in hosts:
            hosts[line[1]].append(l)
        else:
            hosts[line[1]] = [l]

    for host in hosts:
        evidence = hosts[host]
        if isUNLP(host):
            report = dict(
                        type = "malware",
                        hostAddress = host,
                        feed = "spampot"
                    )
            files = {'evidence_file': ("evidence.txt", header+'\n'+'\n'.join(evidence), 'text/plain', {'Expires': '0'})}
            if isUNLP(host):
                #log_info.append(str(evidence))
                response = requests.post(ngen_url_prod_internal, data=report, headers=headers, files=files, verify=False)
                if response.status_code != 201:
                    error = True
                    log_info.append(str(response)+str(response.text)+str(report))
                    log_info.append(str(files))
            elif send_external:
                response = requests.post(ngen_url_prod_external, data=report, headers=headers, files=files, verify=False)
                if response.status_code != 201:
                    error = True
                    log_info.append('\n'+str(response)+'\n'+str(response.text)+'\n'+str(report)+'\n')
                    log_info.append(str(files)+'\n\n')

    # Send info_log via mail
    log_report = '\n'.join(log_info)
    if error:
        maillog.sendError(log_report)
    else:
        maillog.sendInfo("Completed successful")

try:
    header, lines = process_file()
    if header:
        process_lines(header, lines)
except Exception as e:
    et, ev, etb = sys.exc_info()
    time = str(datetime.datetime.now())
    tbinfo = traceback.format_tb(etb)#[0]
    debugmsg = "\nTraceback info:\n" + ''.join(tbinfo) + "\n"
    fullmsg = "exception in SpamPot: \n" + time + debugmsg+str(et.__name__)+":"+str(ev)+"\n"
    maillog.sendError(fullmsg)
    #raise (e)
