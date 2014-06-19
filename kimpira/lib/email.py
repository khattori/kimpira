from __future__ import absolute_import
import email
import email.header
import imaplib
import smtplib
import yaml


def imap4_create(host, port=None, use_ssl=False):
    args = [host]
    if port:
        args.append[port]
    if use_ssl:
        return imaplib.IMAP4_SSL(*args)
    else:
        return imaplib.IMAP4(*args)


def _mail_parse(message):
    dic = dict(message)

    for key, value in dic.items():
        dic[key] = u''
        for s, charset in email.header.decode_header(value):
            if charset:
                dic[key] += unicode(s, charset)
            else:
                dic[key] += unicode(s)

    if message.is_multipart():
        payload = message.get_payload()
        dic['Is-Multipart'] = True
        dic['Body'] = [_mail_parse(x) for x in payload]
    else:
        payload = message.get_payload(decode=True)
        filename = message.get_filename()
        content_type = message.get_content_type()
        if content_type == 'text/plain':
            decode_charset = message.get_content_charset('utf-8')
            payload = payload.decode(decode_charset)
        dic['Is-Multipart'] = False
        dic['Body'] = payload
        dic['Filename'] = filename
    return dic


def recv(runtime, args, op):
    conf_file = runtime._expand_path(args[0])
    with open(conf_file) as f:
        conf = yaml.load(f)

    imap4 = None
    mails = []
    try:
        imap4 = imap4_create(conf['host'], conf.get('port'), conf.get('use_ssl'))
        imap4.login(conf['username'], conf['password'])
        imap4.select()
        _typ, data = imap4.search(None, 'ALL')
        for num in data[0].split():
            typ, ret = imap4.fetch(num, '(RFC822)')
            if typ != 'OK':
                print "*** [email.recv] failed to fetch mail '{0}'".format(num)
                continue
            mail = ret[0][1]
            mails.append(_mail_parse(email.message_from_string(mail)))
            print "*** [email.recv] fetched mail '{0}'".format(num)
            typ, ret = imap4.store(num, '+FLAGS', '\\Deleted')
            if typ != 'OK':
                print "*** [email.recv] failed to delete mail '{0}'".format(num)
                continue
        imap4.expunge()
    except Exception, e:
        print "*** [email.recv] failed to fetch mails: {0}".format(e)
    finally:
        if imap4:
            imap4.logout()
    return mails


def send(runtime, args, op):
    pass
