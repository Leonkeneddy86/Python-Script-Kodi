import os
import asyncio
import shutil
import time
import zipfile
import py7zr
import rarfile
import subprocess
from telethon import types
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename
from telethon.errors import SessionPasswordNeededError

# Configuración
API_ID = ''
API_HASH = ''
PHONE_NUMBER = ''
SESSION_FILE = 'mi_sesion'

# IDs de los canales (reemplaza con los IDs reales)
CHANNEL_ID_1 = -1000000000  # Ejemplo de ID para el primer canal
CHANNEL_ID_2 = -100200000 # Ejemplo de ID para el segundo canal
CONTROL_CHANNEL_ID = -10000000  # ID del canal de control

# Directorios para guardar los archivos
SAVE_DIR_1 = '/home/deck/Downloads/Bot/Movies/.temp/'
SAVE_DIR_2 = '/home/deck/Downloads/Bot/Series/.temp/'
EXTRACT_DIR_1 = '/home/deck/Downloads/Bot/Movies/'
EXTRACT_DIR_2 = '/home/deck/Downloads/Bot/Series/'

# Tiempo de espera entre cada ciclo de revisión (en segundos)
WAIT_TIME = 15  # 1 minuto

# Configuración de TinyMediaManager
USE_TMM = True  # Activar/desactivar TinyMediaManager
TMM_CHANNEL_ID_1_COMMAND = "/home/deck/Applications/tinyMediaManager/./tinyMediaManager movie -u -n -r"
TMM_CHANNEL_ID_2_COMMAND = "/home/deck/Applications/tinyMediaManager/./tinyMediaManager tvshow -u -n -r"

# Configuración de descarga y reintentos
DOWNLOAD_RETRIES = 6  # Número máximo de intentos para descargar un archivo
DOWNLOAD_TIMEOUT = 20  # Timeout en segundos por intento

# Variable para controlar la ejecución
is_running = False

def get_file_name(message):
    for attr in message.document.attributes:
        if isinstance(attr, types.DocumentAttributeFilename):
            return attr.file_name
    return f"unknown_file_{message.id}"

def join_multipart_files(base_file_path):
    dir_path = os.path.dirname(base_file_path)
    file_name = os.path.basename(base_file_path)
    file_name_without_ext = os.path.splitext(file_name)[0]

    if file_name.endswith(('.7z.001', '.zip.001')):
        parts = sorted([f for f in os.listdir(dir_path) if f.startswith(file_name_without_ext)])
        output_file = os.path.join(dir_path, file_name_without_ext)

        with open(output_file, 'wb') as outfile:
            for part in parts:
                with open(os.path.join(dir_path, part), 'rb') as infile:
                    shutil.copyfileobj(infile, outfile)

        print(f"Partes unidas en: {output_file}")
        return output_file

    else:
        return base_file_path

async def extract_file(file_path, extract_dir):
    file_extension = os.path.splitext(file_path)[1].lower()

    try:
        if file_extension == '.zip':
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        elif file_extension == '.7z':
            with py7zr.SevenZipFile(file_path, mode='r') as z:
                z.extractall(extract_dir)
        elif file_extension == '.rar':
            with rarfile.RarFile(file_path) as rar_ref:
                rar_ref.extractall(extract_dir)
        else:
            raise ValueError(f"Formato de archivo no soportado para extracción: {file_extension}")

        print(f"Archivo extraído: {file_path}")
        os.remove(file_path)
        return True

    except Exception as e:
        print(f"Error al extraer {file_path}: {str(e)}")
        dest_path = os.path.join(extract_dir, os.path.basename(file_path))
        shutil.move(file_path, dest_path)
        print(f"Archivo movido debido a error: {dest_path}")
        return False

async def process_grouped_files(client, message, save_dir, extract_dir):
    if message.grouped_id is None:
        return await process_single_file(client, message, save_dir, extract_dir)

    max_amp = 10
    search_ids = list(range(message.id - max_amp, message.id + max_amp + 1))
    messages = await client.get_messages(message.chat_id, ids=search_ids)
    group_files = [msg for msg in messages if msg and msg.grouped_id == message.grouped_id and msg.document]

    if not group_files:
        print("No se encontraron archivos en el grupo.")
        return message.id, False

    grouped_id_folder = None
    print(f"Se detectó un grupo con ID: {message.grouped_id}")

    user_response = input("¿Deseas guardar estos archivos en una carpeta nueva en el destino? (Y/N): ").strip().lower()

    if user_response == 'y':
        grouped_id_folder = input("Introduce el nombre de la carpeta: ").strip()
        if not grouped_id_folder:
            print("No se proporcionó un nombre válido para la carpeta.")
            return message.id, False

        destination_folder = os.path.join(extract_dir, grouped_id_folder)
        os.makedirs(destination_folder, exist_ok=True)
        print(f"Carpeta creada: {destination_folder}")
    else:
        print("Opción no seleccionada. Procediendo con la descarga y extracción.")

    file_paths = []
    is_archive = False
    archive_type = None
    rar_main_file = None

    for part in group_files:
        file_name = get_file_name(part)
        file_path = os.path.join(save_dir, file_name)
        file_paths.append(file_path)

        print(f"Descargando parte: {file_name}")
        await client.download_media(part, file_path)
        print(f"Parte descargada: {file_name}")

        if file_name.endswith('.7z.001'):
            is_archive = True
            archive_type = '7z'
        elif file_name.endswith('.zip.001'):
            is_archive = True
            archive_type = 'zip'
        elif file_name.endswith('.part1.rar'):
            is_archive = True
            archive_type = 'rar'
            rar_main_file = file_path

    files_processed = False

    if is_archive:
        if archive_type in ['7z', 'zip']:
            joined_file_path = join_multipart_files(file_paths[0])
            files_processed = await extract_file(joined_file_path, destination_folder if grouped_id_folder else extract_dir)
        elif archive_type == 'rar':
            files_processed = await extract_file(rar_main_file, destination_folder if grouped_id_folder else extract_dir)

        for file_path in file_paths:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        for file_path in file_paths:
            dest_path = os.path.join(destination_folder if grouped_id_folder else extract_dir, os.path.basename(file_path))
            shutil.move(file_path, dest_path)
            print(f"Archivo movido: {dest_path}")

        files_processed = True

    for part in group_files:
        await delete_message(client, part)

    return max(msg.id for msg in group_files), files_processed

async def process_single_file(client, message, save_dir, extract_dir):
    file_name = get_file_name(message)
    file_path = os.path.join(save_dir, file_name)

    print(f"Descargando: {file_name}")
    await client.download_media(message, file_path)

    print(f"Descarga completada: {file_name}")

    dest_path = os.path.join(extract_dir, file_name)

    shutil.move(file_path, dest_path)

    print(f"Archivo movido: {dest_path}")

    await delete_message(client, message)

    return message.id, True

async def delete_message(client, message):
    try:
        await client.delete_messages(message.chat_id, message.id)
        print(f"Mensaje borrado del canal: {message.id}")

    except Exception as e:
        print(f"Error al borrar el mensaje {message.id}: {str(e)}")

async def download_and_delete_media(client, message, save_dir, extract_dir):
    if message.media:
        return await process_grouped_files(client, message, save_dir, extract_dir)

    else:
        print("El mensaje no contiene media.")

    return message.id, False

def execute_tmm(command):
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"Comando TMM ejecutado: {command}")

    except subprocess.CalledProcessError as e:
        print(f"Error al ejecutar el comando TMM: {e}")

async def process_channel(client, channel_id, save_dir, extract_dir, last_message_id, tmm_command):
    try:
        channel = await client.get_entity(channel_id)

        print(f"Procesando canal: {channel.title}")

        files_processed = False

        async for message in client.iter_messages(channel, min_id=last_message_id):
            if not is_running:
                break

            new_last_id, processed = await download_and_delete_media(client, message, save_dir, extract_dir)

            last_message_id = max(last_message_id, new_last_id)

            files_processed |= processed

        if files_processed:
            execute_tmm(tmm_command)

        return last_message_id

    except Exception as e:
       print(f"Error al procesar el canal {channel_id}: {str(e)}")
       return last_message_id

async def check_directories():
   directories = [SAVE_DIR_1, SAVE_DIR_2, EXTRACT_DIR_1, EXTRACT_DIR_2]
   for directory in directories:
       if not os.path.exists(directory):
           print(f"La carpeta {directory} no existe. Creándola...")
           os.makedirs(directory)

   return True

async def main_loop(client):
   global is_running

   last_message_id_1 = 0
   last_message_id_2 = 0

   while is_running:
       try:
           if not await check_directories():
               print(f"Esperando {WAIT_TIME} segundos antes del próximo intento...")
               await asyncio.sleep(WAIT_TIME)
               continue

           last_message_id_1 = await process_channel(client,
                                                      CHANNEL_ID_1,
                                                      SAVE_DIR_1,
                                                      EXTRACT_DIR_1,
                                                      last_message_id_1,
                                                      TMM_CHANNEL_ID_1_COMMAND)

           last_message_id_2=await process_channel(client,
                                                    CHANNEL_ID_2,
                                                    SAVE_DIR_2,
                                                    EXTRACT_DIR_2,
                                                    last_message_id_2,
                                                    TMM_CHANNEL_ID_2_COMMAND)

           print(f"Ciclo de revisión completado. Esperando {WAIT_TIME} segundos...")
           await asyncio.sleep(WAIT_TIME)

       except Exception as e:
           print(f"Error en el ciclo principal: {str(e)}")
           await asyncio.sleep(WAIT_TIME)

async def main():
   client=TelegramClient(SESSION_FILE,
                          API_ID,
                          API_HASH)

   await client.start()

   if not await client.is_user_authorized():
       await client.send_code_request(PHONE_NUMBER)

       try:
           await client.sign_in(PHONE_NUMBER,input('Enter the code: '))
       except SessionPasswordNeededError:
           await client.sign_in(password=input('Password: '))

   @client.on(events.NewMessage(chats=CONTROL_CHANNEL_ID))
   async def command_handler(event):
       global is_running

       if event.raw_text == "/start":
           if not is_running:
               is_running=True
               await event.reply("Script iniciado.")
               await main_loop(client)
           else:
               await event.reply("El script ya está en ejecución.")

       elif event.raw_text == "/stop":
           if is_running:
               is_running=False
               await event.reply("Script detenido.")
           else:
               await event.reply("El script no está en ejecución.")

   print("Bot de control iniciado. Esperando comandos...")
   await client.run_until_disconnected()

if __name__ == '__main__':
   asyncio.run(main())
