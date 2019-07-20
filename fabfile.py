# -*- coding: UTF-8 -*-
# fabfile.py
import os, re, tarfile
from datetime import datetime

from fabric.api import *

env.user = 'fanco'
env.sudo_user = 'root'
env.hosts = ['3.9.215.67']

db_user = 'test'
db_password = '1234'

_TAR_FILE = 'dist-awesome.tar.gz'

_REMOTE_TMP_TAR = '/tmp/%s' % _TAR_FILE

_REMOTE_BASE_DIR = '/srv/train4py'

def _current_path():
	return os.path.abspath('.')

def _now():
	return datetime.now().strftime('%y-%m-%d_%H.%M.%S')

def backup():
	'''
	Dump entire database on server and backup to local.
	'''
	dt = _now()
	f = 'backup-awesome-%s.sql' % dt
	with cd('/tmp'):
		run('mysqldump --user=%s --password=%s --skip-opt --add-drop-table --default-character-set=utf8 --quick awesome > %s' % (db_user, db_password, f))
		run('tar -czvf %s.tar.gz %s' % (f, f))
		get('%s.tar.gz' % f, '%s/backup/' % _current_path())
		run('rm -f %s' % f)
		run('rm -f %s.tar.gz' % f)

def build():
	'''
	Build dist package.
	'''
	local('del dist\\%s' % _TAR_FILE)                   
	tar = tarfile.open("dist/%s" % _TAR_FILE,"w:gz")    
	for root,_dir,files in os.walk("www/"):            
		for f in files:
			if not (('.pyc' in f) or ('.pyo' in f)):
				fullpath = os.path.join(root,f)
				tar.add(fullpath)
	tar.close()


def deploy():
	newdir = 'www-%s' % _now()
	run('rm -f %s' % _REMOTE_TMP_TAR)
	put('dist/%s' % _TAR_FILE, _REMOTE_TMP_TAR)
	with cd(_REMOTE_BASE_DIR):
		sudo('mkdir %s' % newdir)
	with cd('%s/%s' % (_REMOTE_BASE_DIR, newdir)):
		sudo('tar -xzvf %s' % _REMOTE_TMP_TAR)
		sudo('mv www/* .')  
		sudo('rm -rf www')
		#sudo('dos2unix app.py')     
		sudo('chmod a+x app.py')      
	with cd(_REMOTE_BASE_DIR):
		sudo('rm -f www')
		sudo('ln -s %s www' % newdir)
		sudo('chown fanco:fanco www')
		sudo('chown -R fanco:fanco %s' % newdir)
	with settings(warn_only=True):
		sudo('supervisorctl stop awesome')
		sudo('supervisorctl start awesome')
		sudo('/etc/init.d/nginx reload')

RE_FILES = re.compile('\r?\n')

def rollback():
	'''
	rollback to previous version
	'''
	with cd(_REMOTE_BASE_DIR):
		r = run('ls -p -1')
		files = [s[:-1] for s in RE_FILES.split(r) if s.startswith('www-') and s.endswith('/')]
		files.sort(cmp=lambda s1, s2: 1 if s1 < s2 else -1)
		r = run('ls -l www')
		ss = r.split(' -> ')
		if len(ss) != 2:
			print ('ERROR: \'www\' is not a symbol link.')
			return
		current = ss[1]
		print ('Found current symbol link points to: %s\n' % current)
		try:
			index = files.index(current)
		except ValueError, e:
			print ('ERROR: symbol link is invalid.')
			return
		if len(files) == index + 1:
			print ('ERROR: already the oldest version.')
		old = files[index + 1]
		print ('==================================================')
		for f in files:
			if f == current:
				print ('      Current ---> %s' % current)
			elif f == old:
				print ('  Rollback to ---> %s' % old)
			else:
				print ('                   %s' % f)
		print ('==================================================')
		print ('')
		yn = raw_input ('continue? y/N ')
		if yn != 'y' and yn != 'Y':
			print ('Rollback cancelled.')
			return
		print ('Start rollback...')
		sudo('rm -f www')
		sudo('ln -s %s www' % old)
		sudo('chown fanco:fanco www')
		with settings(warn_only=True):
			sudo('supervisorctl stop awesome')
			sudo('supervisorctl start awesome')
			sudo('/etc/init.d/nginx reload')
		print ('ROLLBACKED OK.')

def restore2local():
	'''
	Restore db to local
	'''
	backup_dir = os.path.join(_current_path(), 'backup')
	fs = os.listdir(backup_dir)
	files = [f for f in fs if f.startswith('backup-') and f.endswith('.sql.tar.gz')]
	files.sort(cmp=lambda s1, s2: 1 if s1 < s2 else -1)
	if len(files)==0:
		print 'No backup files found.'
		return
	print ('Found %s backup files:' % len(files))
	print ('==================================================')
	n = 0
	for f in files:
		print ('%s: %s' % (n, f))
		n = n + 1
	print ('==================================================')
	print ('')
	try:
		num = int(raw_input ('Restore file: '))
	except ValueError:
		print ('Invalid file number.')
		return
	restore_file = files[num]
	yn = raw_input('Restore file %s: %s? y/N ' % (num, restore_file))
	if yn != 'y' and yn != 'Y':
		print ('Restore cancelled.')
		return
	print ('Start restore to local database...')
	p = raw_input('Input mysql root password: ')
	sqls = [
		'drop database if exists awesome;',
		'create database awesome;',
		'grant select, insert, update, delete on awesome.* to \'%s\'@\'localhost\' identified by \'%s\';' % (db_user, db_password)
	]
	for sql in sqls:
		local(r'mysql -uroot -p%s -e "%s"' % (p, sql))
	extract('backup\\%s' % restore_file, 'backup\\')
	with lcd('backup'):
		local(r'mysql -uroot -p%s --default-character-set=utf8 awesome < %s' % (p, restore_file[:-7]))
		local('del %s' % restore_file[:-7])