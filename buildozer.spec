[app]
title = LM Palabras
package.name = lmpalabras
package.domain = org.lm
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_dirs = .github,bin,.buildozer,__pycache__
version = 1.0
requirements = python3,kivy==2.3.0,openpyxl,et_xmlfile,pyjnius,android,androidstorage4kivy
orientation = portrait
fullscreen = 0
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
