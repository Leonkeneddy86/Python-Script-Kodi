
# Robingood


What make the difference?

This script its not only a typical telegram downloader, it could monitor 2 channels and each channel execute a tinyMediaManager command, so let your kodi media gallery ready for offline use. Also, it let the option to create a folder for grouped_id (nested message) so it will be suitable for tv shows. When the downloads are ready, join and extract 7z/zip/rar multipart files.

How to configure?

fill this configuration variables in top of the robingood.py

# Configuration
API_ID = ''
API_HASH = ''
PHONE_NUMBER = ''
SESSION_FILE = 'mi_sesion'

#IDs channels

CHANNEL_ID_1 = -1000000000 # Canal 1 (Movies)
CHANNEL_ID_2 = -100000000 # Canal 2 (Series)
CONTROL_CHANNEL_ID = -10000000 # Canal de control

#Dirs

SAVE_DIR_1 = '/home/user/Downloads/Bot/Movies/.temp/'

SAVE_DIR_2 = '/home/user/Downloads/Bot/Series/.temp/'

EXTRACT_DIR_1 = '/home/user/Downloads/Bot/Movies/'

EXTRACT_DIR_2 = '/home/user/Downloads/Bot/Series/'

#wait time loop

WAIT_TIME = 15  # 15 segundos

# configurable messages
- MESSAGE_PROMPT_FOLDER = "Se detectó un grupo con ID `{grouped_id}`. ¿Quieres guardar los archivos en una carpeta nueva? Responde con `Y` o `N`."
- MESSAGE_ENTER_FOLDER_NAME = "Por favor, introduce el nombre de la carpeta:"
- MESSAGE_TIMEOUT_FOLDER = "No se recibió respuesta. Procediendo con la descarga y extracción."
- MESSAGE_FOLDER_CREATED = "Carpeta `{folder_name}` creada exitosamente."
- MESSAGE_PROCESS_COMPLETE = "Archivos del grupo `{grouped_id}` procesados y guardados en `{folder_path}`."
- MESSAGE_NO_FILES_FOUND = "No se encontraron archivos en el grupo."



# tinyMediaManager (alias TMM)

Start first in GUI mode, configure paths and options. Then the script calls when the downloads task are ended.


3 Channels: Control,Chnanel1(movies), Channel2(TvShows)

# Control channel commands

- /start Start when ready to listen
- /stop kills the process. The systemd service must restart the process
- /TMM execute TMM in the 2 channels manually.
