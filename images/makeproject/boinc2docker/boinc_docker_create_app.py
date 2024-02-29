import argparse
import time
import pwd
import os
from functools import partial
import subprocess
from zipfile import ZipFile
from inspect import currentframe
from textwrap import dedent
from itertools import groupby
from shutil import copy
import stat
from os.path import join, exists, basename, dirname, abspath

sh = lambda cmd: subprocess.check_output(['sh','-c',cmd])

# constructs a function that can format a given string s using both global variables 
#and local variables from a specific frame f
fmt = partial(lambda s,f: s.format(**dict(globals(),**f.f_locals)),f=currentframe())

def create_directories(dir):
    if not exists(dir):
    	os.makedirs(dir)


def download(f, appfolder):
    tgt = join(appfolder, basename(f))
    sh('wget --progress=bar:force --content-disposition --no-check-certificate %s -O %s' % (f, tgt))
    return tgt


def get_wrapper(platform, appfolder, wrapper):
    """
    Download and unzip wrapper executables from http://boinc.berkeley.edu/dl
    """
    wrapper_root = "wrapper_" + wrapper[platform] + "_" + platform
    wrapper_file = join(appfolder, wrapper_root +
                        ('.exe' if 'windows' in platform else ''))
    if not exists(wrapper_file):
        with ZipFile(download('http://boinc.berkeley.edu/dl/' + wrapper_root + '.zip', appfolder)) as zf:
            with open(wrapper_file, 'wb') as f:
                zi = {basename(z.filename): z for z in zf.filelist}[
                    basename(wrapper_file)]
                f.write(zf.read(zi))
                os.fchmod(f.fileno(), 0o775)

    return wrapper_file


def create_job_description_file(app_name, appfolder):

	fmt = partial(lambda s,f: s.format(**dict(globals(),**f.f_locals)),f=currentframe())

	job_content = fmt(dedent("""
					<job_desc>
						<task>
							<application>{app_name}</application>
						</task>
					</job_desc>
					
					"""))

	job_path = appfolder + "/" + app_name + ".xml"
	job_file = open(job_path, "w")
	job_file.write(job_content)
	job_file.close()

	return 0


def create_version_desc(wrapper_file, app_name, appfolder):
	
	fmt = partial(lambda s,f: s.format(**dict(globals(),**f.f_locals)),f=currentframe())

	wrapper = basename(wrapper_file)

	version_content = fmt(dedent("""
					<version>
						<file>
							<physical_name>{wrapper}</physical_name>
							<main_program/>
						</file>
						<file>
							<physical_name>{app_name}</physical_name>
					  		<logical_name>{app_name}</logical_name>
						</file>
	
						<file>
							<physical_name>{app_name}.xml</physical_name>
							<logical_name>job.xml</logical_name>
						</file>
					</version>
					
					"""))
	

	version_path = appfolder + "/" + "version.xml"
	version_file = open(version_path, "w")
	version_file.write(version_content)
	version_file.close()

	return 0


def create_template_in(app_name, uid, gid):

	fmt = partial(lambda s,f: s.format(**dict(globals(),**f.f_locals)),f=currentframe())

	template_name = "/home/boincadm/project/templates/" + app_name + "_in"

	template_in_content =fmt(dedent("""<?xml version=\"1.0\"?>
					<input_template>
   				 		<file_info>
							<number>0</number>
   				 		</file_info>
   				 		<workunit>
       							 <file_ref>
           					 		<file_number>0</file_number>
           					 		<open_name>shared/boinc_app</open_name>
           					 		<copy_file/>
       					 		</file_ref>
    						</workunit>
					</input_template>"""))


	template_in = open(template_name, "w")
	template_in.write(template_in_content)
	template_in.close()

	os.chown(template_name, uid, gid)

	return 0

def create_template_out(app_name, uid, gid):

	fmt = partial(lambda s,f: s.format(**dict(globals(),**f.f_locals)),f=currentframe())

	template_name = "/home/boincadm/project/templates/" + app_name + "_out"

	template_out_content =fmt(dedent("""<?xml version="1.0"?>

						<output_template>

								<file_info>
									<name><OUTFILE_0/>.tgz</name>
									<generated_locally/>
									<upload_when_present/>
									<max_nbytes>134217728</max_nbytes>
									<url><UPLOAD_URL/></url>
								</file_info>

								<result>
									<file_ref>
											<file_name><OUTFILE_0/>.tgz</file_name>
											<open_name>shared/results.tgz</open_name>
											<copy_file>1</copy_file>
											<optional>1</optional>
									</file_ref>
								</result>

						</output_template>
						"""))


	template_out = open(template_name, "w")
	template_out.write(template_out_content)
	template_out.close()

	os.chown(template_name, uid, gid)

	return 0

def create_sign_keys(uid, gid):

	with open("config.xml", "r+") as config:
		contents = config.readlines()
		for line in contents:
			if "key_dir" in line:
				key_dir = (line.split(">"))[1].split("<")[0]
	
	generate_code_sign_key = "/home/boincadm/project/bin/crypt_prog -genkey 1024 " + key_dir + "/code_sign_private " + key_dir + "/code_sign_public"

	generate_upload_key = "/home/boincadm/project/bin/crypt_prog -genkey 1024 " + key_dir + "/upload_private " + key_dir + "/upload_public"

	if not os.path.isdir(key_dir):
		create_directories(key_dir)

	if not os.path.isfile(key_dir + "/upload_private"):
			subprocess.call(generate_upload_key, shell=True)
	


	if not os.path.isfile(key_dir + "/code_sign_private"):
			subprocess.call(generate_code_sign_key, shell=True)

	keys = ["/code_sign_private", "/code_sign_public", "/upload_private", "/upload_public"]
	for i in keys:
		os.chown(key_dir + i, uid, gid)

	return 0

def make_docker_script(appfolder, app_name):

	fmt = partial(lambda s,f: s.format(**dict(globals(),**f.f_locals)),f=currentframe())

	script = fmt(dedent("""
		#!/bin/sh
		docker ps -a
		docker image list
	"""))

	docker_script_path = appfolder + "/" + app_name

	docker_script = open(docker_script_path, "w")
	docker_script.write(script)
	docker_script.close()

	os.chmod(docker_script_path, stat.S_IRWXU | stat.S_IRWXG)

	return 0


def add_new_app_to_project(app_name):

	line = "    <app>\n" + "        <name>" + app_name + "</name>\n" + \
    		"        <user_friendly_name>" + app_name + \
    		"</user_friendly_name>\n" + "    </app>\n"

	with open("project.xml", "r+") as project_config:
		contents = project_config.readlines()
		len_contents = len(contents)
		for i in range(len_contents):
			if i == (len_contents - 2):
				contents.insert(i, line)

	with open("project.xml", "r") as file:
		file.close()

	with open("project.xml", "w") as project_config:
		project_config.writelines(contents)

# def create_input_files():

def add_new_app(app_name):

	uid = pwd.getpwnam('boincadm').pw_uid
        gid = pwd.getpwnam('boincadm').pw_gid

	# stop all daemons for adding new app
	subprocess.call("/home/boincadm/project/bin/stop")

	#path for app directories
	approot = "/home/boincadm/project/"

	app_path = ["apps", app_name, "1.0.0"]

	for path in app_path:
		approot = approot + path + "/"
		create_directories(approot)
		os.chown(approot, uid, gid)

	print(approot)

	#get wrapper, version, docker_script, job.xml to app_directories
	platforms = ["x86_64-pc-linux-gnu", "windows_x86_64", "x86_64-apple-darwin"]
	wrapper = {"x86_64-pc-linux-gnu": "26015", "windows_x86_64": "26015", "x86_64-apple-darwin":"26015"}
	for platform in platforms:

		# create app directories
		appfolder = join(approot, platform + '__vbox64_mt')
		create_directories(appfolder)
		os.chown(appfolder, uid, gid)

		# get wrapper
		wrapper_file = get_wrapper(platform, appfolder, wrapper)
		os.chown(wrapper_file, uid, gid)

		print("create app version")

		# create version description
		create_version_desc(wrapper_file, app_name, appfolder)
		os.chown(appfolder + "/version.xml", uid, gid)

		print("create docker script")

		# create docker script
		make_docker_script(appfolder, app_name)
		os.chown(appfolder + "/" + app_name, uid, gid)

		print("create job file")

		# create job.xml file
		create_job_description_file(app_name, appfolder)
		os.chown(appfolder + "/" + app_name + ".xml", uid, gid)

		if platform != "windows_x86_64":
			if os.path.isfile(wrapper_file + ".zip"):
				os.remove(wrapper_file + ".zip")
		else:
			if os.path.isfile(appfolder + "/wrapper_26015_windows_x86_64.zip"):
				os.remove(appfolder + "/wrapper_26015_windows_x86_64.zip")

	print("add the application to the project")

	#add new application to project.xml
	add_new_app_to_project(app_name)

	print("create template_in")

	#create template_in
	create_template_in(app_name, uid, gid)

	print("create template_out")

	#create template_out
	create_template_out(app_name, uid, gid)

	create_sign_keys(uid, gid)

	print("run command bin/xadd for adding new application")

	# run command bin/xadd for adding new application
	subprocess.call("/home/boincadm/project/bin/xadd")

	print("run command bin/update_versions for adding application version")

	subprocess.call("/home/boincadm/project/bin/update_versions")

	# run command bin/update_versions for adding application version

	print("start daemons")

	# start daemons
	subprocess.call("/home/boincadm/project/bin/start")

	os.chown("/home/boincadm/project/download/" + app_name, uid, gid)
	
	os.chown("/home/boincadm/project/download/" + app_name + ".xml", uid, gid)

	for i in wrapper:
		if i != "windows_x86_64":
			os.chown("/home/boincadm/project/download/wrapper_" + wrapper[i] + "_" + i, uid, gid)
		else:
			os.chown("/home/boincadm/project/download/wrapper_" + wrapper[i] + "_" + i + ".exe", uid, gid)

if __name__=='__main__':
	parser = argparse.ArgumentParser(prog='add_new_app')
	parser.add_argument('--appname', default='boinc_docker', help='appname (default: boinc2docker)')

	args = parser.parse_args()

	add_new_app(app_name=args.appname)
