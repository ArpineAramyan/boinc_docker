import subprocess
import os
from os.path import join, exists, basename
from zipfile import ZipFile
import xml.etree.cElementTree as ET
from xml.dom import minidom
from functools import partial
from textwrap import dedent
from inspect import currentframe
import pwd
import stat

def create_directories(dir):
        if not exists(dir):
            os.makedirs(dir)

def sh(cmd):
    return subprocess.check_output(cmd,shell=True,stderr=subprocess.STDOUT).strip()

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

def create_version_desc(wrapper_file, app_name, appfolder):

        wrapper = basename(wrapper_file)

        if "windows" in wrapper:
            ok_app_name = app_name + ".bat"
        else:
            ok_app_name = app_name

        root = ET.Element("version")

        fileinfo = ET.SubElement(root, "file")
        ET.SubElement(fileinfo, "physical_name").text = wrapper
        ET.SubElement(fileinfo, "main_program")

        fileinfo = ET.SubElement(root, "file")
        ET.SubElement(fileinfo, "physical_name").text = ok_app_name
        ET.SubElement(fileinfo, "logical_name").text = app_name

        fileinfo = ET.SubElement(root, "file")
        ET.SubElement(fileinfo, "physical_name").text = app_name + ".xml"
        ET.SubElement(fileinfo, "logical_name").text = "job.xml"


        version_path = appfolder + "/" + "version.xml"
        open(version_path,'w').write(minidom.parseString(ET.tostring(root, 'utf-8')).toprettyxml(indent=" "*4))

def create_script(appfolder, app_name, platform):

        fmt = partial(lambda s,f: s.format(**dict(globals(),**f.f_locals)),f=currentframe())

        if "windows" in platform:
            script = fmt(dedent("""wsl chmod 777 %1
wsl bash %1"""))

        else:
            script = fmt(dedent("""#!/bin/bash
chmod 777 $1

./$1"""))

        script_path = appfolder + "/" + app_name + (".bat" if "windows" in platform else "")

        with open(script_path, "w") as script_create:
                script_create.write(script)

        os.chmod(script_path, stat.S_IRWXU | stat.S_IRWXG)

def create_job_description_file(app_name, appfolder):
     
        root = ET.Element("job_desc")

        task = ET.SubElement(root, "task")

        ET.SubElement(task, "physical_name").text = app_name
        ET.SubElement(task, "command_line").text = "boinc_docker"

        job_path = appfolder + "/" + app_name + ".xml"

        open(job_path,'w').write(minidom.parseString(ET.tostring(root, 'utf-8')).toprettyxml(indent=" "*4))

def add_new_app_to_project(app_name):

	line = "    <app>\n" + "        <name>" + app_name + "</name>\n" + \
    		"        <user_friendly_name>" + app_name + \
    		"</user_friendly_name>\n" + "    </app>\n"

	with open("project.xml", "r+") as project_config:
		contents = project_config.readlines()
		len_contents = len(contents)
		for i in range(len_contents):
			if i == (len_contents - 1):
				contents.insert(i, line)

	with open("project.xml", "r") as file:
		file.close()

	with open("project.xml", "w") as project_config:
		project_config.writelines(contents)


def create_sign_keys(uid, gid):

        with open("config.xml", "r+") as config:
            contents = config.readlines()
            for line in contents:
                if "key_dir" in line:
                    key_dir = (line.split(">"))[1].split("<")[0]

        create_directories(key_dir)

        generate_code_sign_key = "/home/boincadm/project/bin/crypt_prog -genkey 1024 " + key_dir + "/code_sign_private " + key_dir + "/code_sign_public"

        generate_upload_key = "/home/boincadm/project/bin/crypt_prog -genkey 1024 " + key_dir + "/upload_private " + key_dir + "/upload_public"

        if not os.path.isdir(key_dir):
            create_directories(key_dir)

        if not os.path.isfile(key_dir + "/upload_private"):
            sh(generate_upload_key, shell=True)


        if not os.path.isfile(key_dir + "/code_sign_private"):
            sh(generate_code_sign_key, shell=True)

        keys = ["/code_sign_private", "/code_sign_public", "/upload_private", "/upload_public"]
        for i in keys:
            os.chown(key_dir + i, uid, gid)

def add_new_app(app_name, image, plan_class_name, input_files, ngpus, output_files_names):

        uid = pwd.getpwnam('boincadm').pw_uid
        gid = pwd.getpwnam('boincadm').pw_gid

        # stop all daemons for adding new app
        sh("/home/boincadm/project/bin/stop")

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
                appfolder = join(approot, platform + '__' + plan_class_name)
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
                create_script(appfolder, app_name, platform)
                if "windows" in platform:
                    os.chown(appfolder + "/" + app_name + ".bat", uid, gid)
                else: 
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

        create_sign_keys(uid, gid)

        print("run command bin/xadd for adding new application")

        # run command bin/xadd for adding new application
        sh("/home/boincadm/project/bin/xadd")

        print("run command bin/update_versions for adding application version")

        sh("yes | /home/boincadm/project/bin/update_versions")

        # run command bin/update_versions for adding application version

        print("start daemons")

        # start daemons
        sh("/home/boincadm/project/bin/start")

        os.chown("/home/boincadm/project/download/" + app_name + ".bat", uid, gid)
        os.chown("/home/boincadm/project/download/" + app_name, uid, gid)

        os.chown("/home/boincadm/project/download/" + app_name + ".xml", uid, gid)

        for i in wrapper:
            if i != "windows_x86_64":
                os.chown("/home/boincadm/project/download/wrapper_" + wrapper[i] + "_" + i, uid, gid)
            else:
                os.chown("/home/boincadm/project/download/wrapper_" + wrapper[i] + "_" + i + ".exe", uid, gid)