#!/usr/bin/env python3
import os
import asyncio
import shutil
import zipfile
import py7zr
import rarfile
import subprocess
import signal  # Importar el módulo signal
import json
from telethon import TelegramClient, events, types
from telethon.errors import SessionPasswordNeededError, RPCError

# Configuración
API_ID = ''
API_HASH = ''
PHONE_NUMBER = ''
SESSION_FILE = 'mi_sesion'

# IDs de los canales
CHANNEL_ID_1 = -1000000000 # Canal 1 (Movies)
CHANNEL_ID_2 = -100000000 # Canal 2 (Series)
CONTROL_CHANNEL_ID = -10000000 # Canal de control

# Directorios para guardar y extraer archivos
SAVE_DIR_1 = '/home/user/Downloads/Bot/Movies/.temp/'
SAVE_DIR_2 = '/home/user/Downloads/Bot/Series/.temp/'
EXTRACT_DIR_1 = '/home/user/Downloads/Bot/Movies/'
EXTRACT_DIR_2 = '/home/user/Downloads/Bot/Series/'

# Tiempo de espera entre cada ciclo de revisión (en segundos)
WAIT_TIME = 15  # 15 segundos

# Configuración de TinyMediaManager
USE_TMM = True
TMM_CHANNEL_ID_1_COMMAND = "/home/deck/Applications/tinyMediaManager/./tinyMediaManager movie -u -n -r"
TMM_CHANNEL_ID_2_COMMAND = "/home/deck/Applications/tinyMediaManager/./tinyMediaManager tvshow -u -n -r"

# Mensajes configurables
MESSAGE_PROMPT_FOLDER = "Se detectó un grupo con ID `{grouped_id}`. ¿Quieres guardar los archivos en una carpeta nueva? Responde con `Y` o `N`."
MESSAGE_ENTER_FOLDER_NAME = "Por favor, introduce el nombre de la carpeta:"
MESSAGE_TIMEOUT_FOLDER = "No se recibió respuesta. Procediendo con la descarga y extracción."
MESSAGE_FOLDER_CREATED = "Carpeta `{folder_name}` creada exitosamente."
MESSAGE_PROCESS_COMPLETE = "Archivos del grupo `{grouped_id}` procesados y guardados en `{folder_path}`."
MESSAGE_NO_FILES_FOUND = "No se encontraron archivos en el grupo."

# Variables globales
is_running = False
download_state = {}

# Funciones para guardar y cargar el estado de las descargas
def save_state():
    global STATE_FILE, download_state
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(download_state, f)
        print(f"Estado guardado en {STATE_FILE}")
    except Exception as e:
        print(f"Error al guardar el estado: {e}")

def load_state():
    global STATE_FILE, download_state
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                download_state = json.load(f)
            print(f"Estado cargado desde {STATE_FILE}")
        else:
            download_state = {}
            print(f"Archivo de estado {STATE_FILE} no encontrado, iniciando nuevo estado.")
    except Exception as e:
        print(f"Error al cargar el estado: {e}")
        download_state = {}

def get_file_name(message):
    if message.document is None:
        return None
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
    global download_state
    if message.grouped_id is None:
        return await process_single_file(client, message, save_dir, extract_dir)

    grouped_id = message.grouped_id
    max_amp = 10
    search_ids = list(range(message.id - max_amp, message.id + max_amp + 1))
    messages = await client.get_messages(message.chat_id, ids=search_ids)
    group_files = [msg for msg in messages if msg and msg.grouped_id == grouped_id and msg.document]

    if not group_files:
        await client.send_message(message.chat_id, MESSAGE_NO_FILES_FOUND)
        return message.id, False

    # Si ya se ha guardado el estado de este grupo, usarlo
    if str(grouped_id) in download_state:
        state = download_state[str(grouped_id)]
        destination_folder = state['destination_folder']
        downloaded_files = state['downloaded_files']
    else:
        # Crear una carpeta específica para el grupo sin preguntar de nuevo
        destination_folder = extract_dir
        downloaded_files = []

    file_paths = []
    is_archive = False
    archive_type = None
    rar_main_file = None

    for part in group_files:
        if not is_running:
            print("Deteniendo descarga de archivos agrupados...")
            return message.id, False
        file_name = get_file_name(part)
        if file_name is None or file_name in downloaded_files:
            continue
        file_path = os.path.join(save_dir, file_name)
        file_paths.append(file_path)
        print(f"Descargando parte: {file_name}")
        await client.download_media(part, file_path)

        # Actualizar estado de la descarga
        downloaded_files.append(file_name)
        download_state[str(grouped_id)] = {
            'chat_id': message.chat_id,
            'destination_folder': destination_folder,
            'downloaded_files': downloaded_files
        }
        save_state()

        if file_name.endswith('.7z.001') or file_name.endswith('.zip.001'):
            is_archive = True
            archive_type = '7z' if file_name.endswith('.7z.001') else 'zip'
        elif file_name.endswith('.part1.rar'):
            is_archive = True
            archive_type = 'rar'
            rar_main_file = file_path

    files_processed = False
    if is_archive:
        if archive_type in ['7z', 'zip']:
            joined_file_path = join_multipart_files(file_paths[0])
            files_processed = await extract_file(joined_file_path, destination_folder)
        elif archive_type == 'rar':
            files_processed = await extract_file(rar_main_file, destination_folder)
        for file_path in file_paths:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        for file_path in file_paths:
            dest_path = os.path.join(destination_folder, os.path.basename(file_path))
            shutil.move(file_path, dest_path)
            print(f"Archivo movido: {dest_path}")
        files_processed = True

    # Eliminar estado de descarga completada
    if str(grouped_id) in download_state:
        del download_state[str(grouped_id)]
        save_state()

    await client.send_message(
        message.chat_id,
        MESSAGE_PROCESS_COMPLETE.format(grouped_id=grouped_id, folder_path=destination_folder)
    )

    # Borrar todos los mensajes del grupo después de procesarlos
    for part in group_files:
        await delete_message(client, part)

    return max(msg.id for msg in group_files), files_processed

async def process_single_file(client, message, save_dir, extract_dir):
    global download_state
    if not is_running:
        print("Deteniendo descarga de archivo único...")
        return message.id, False
    file_name = get_file_name(message)
    if file_name is None:
        return message.id, False
    file_path = os.path.join(save_dir, file_name)
    print(f"Descargando: {file_name}")
    await client.download_media(message, file_path)
    dest_path = os.path.join(extract_dir, file_name)
    shutil.move(file_path, dest_path)
    print(f"Archivo movido: {dest_path}")

    # Guardar estado de la descarga
    download_state[message.id] = {
        'chat_id': message.chat_id,
        'file_path': file_path,
        'save_dir': save_dir,
        'extract_dir': extract_dir
    }
    save_state()

    # Eliminar estado de descarga completada
    if message.id in download_state:
        del download_state[message.id]
        save_state()

    await delete_message(client, message)
    return message.id, True

async def delete_message(client, message):
    try:
        await client.delete_messages(message.chat_id, [message.id])
        print(f"Mensaje borrado del canal: {message.id}")
    except Exception as e:
        print(f"Error al borrar el mensaje {message.id}: {str(e)}")

def execute_tmm(command):
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"Comando TMM ejecutado: {command}\nSalida:\n{result.stdout}\nError:\n{result.stderr}")
    except subprocess.CalledProcessError as e:
        print(f"Error al ejecutar el comando TMM: {e}\nSalida:\n{e.output}\nError:\n{e.stderr}")

async def process_channel(client, channel_id, save_dir, extract_dir, last_message_id, tmm_command):
    try:
        channel = await client.get_entity(channel_id)
        print(f"Procesando canal: {channel.title}")
        files_processed = False
        async for message in client.iter_messages(channel, min_id=last_message_id):
            if not is_running:
                print("Deteniendo procesamiento del canal...")
                break
            new_last_id, processed = await process_grouped_files(client, message, save_dir, extract_dir)
            last_message_id = max(last_message_id, new_last_id)
            files_processed |= processed
        if files_processed and USE_TMM:
            execute_tmm(tmm_command)
        return last_message_id
    except RPCError as e:
        print(f"Error RPC al procesar el canal {channel_id}: {str(e)}")
        return last_message_id
    except Exception as e:
        print(f"Error al procesar el canal {channel_id}: {str(e)}")
        return last_message_id

async def resume_downloads(client):
    global download_state
    for message_id, state in download_state.items():
        if not is_running:
            break
        print(f"Resumiendo descarga: {state['file_path']}")
        # Simular la descarga resumida
        await asyncio.sleep(1)  # Simulación de tiempo de descarga
        dest_path = os.path.join(state['extract_dir'], os.path.basename(state['file_path']))
        shutil.move(state['file_path'], dest_path)
        print(f"Archivo movido: {dest_path}")

        # Eliminar estado de descarga completada
        if message_id in download_state:
            del download_state[message_id]
            save_state()

async def main_loop(client):
    global is_running
    load_state()
    last_message_id_1 = 0
    last_message_id_2 = 0
    while is_running:
        try:
            print("Esperando mensajes...")
            await resume_downloads(client)
            last_message_id_1 = await process_channel(client, CHANNEL_ID_1, SAVE_DIR_1, EXTRACT_DIR_1, last_message_id_1, TMM_CHANNEL_ID_1_COMMAND)
            last_message_id_2 = await process_channel(client, CHANNEL_ID_2, SAVE_DIR_2, EXTRACT_DIR_2, last_message_id_2, TMM_CHANNEL_ID_2_COMMAND)
            print("Ciclo completado. Esperando...")
            await asyncio.sleep(WAIT_TIME)
        except Exception as e:
            print(f"Error en el ciclo principal: {str(e)}")
            await asyncio.sleep(WAIT_TIME)

async def start_loop(client):
    global is_running
    is_running = True
    await main_loop(client)

def stop_loop():
    global is_running
    is_running = False
    # Guardar estado de todas las descargas en curso
    save_state()
    print("Loop detenido.")
    os.kill(os.getpid(), signal.SIGTERM)  # Matar el proceso

async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()

    if not await client.is_user_authorized():
        await client.send_code_request(PHONE_NUMBER)
        try:
            await client.sign_in(PHONE_NUMBER, input('Enter the code: '))
        except SessionPasswordNeededError:
            await client.sign_in(password=input('Password: '))

    @client.on(events.NewMessage(chats=CONTROL_CHANNEL_ID))
    async def command_handler(event):
        global is_running
        if event.raw_text == "/start":
            if not is_running:
                await event.reply("Script iniciado.")
                await start_loop(client)
            else:
                await event.reply("El script ya está en ejecución.")
        elif event.raw_text == "/stop":
            if is_running:
                await event.reply("Script detenido.")
                stop_loop()
        elif event.raw_text == "/TMM":
            await event.reply("Ejecutando TinyMediaManager...")
            execute_tmm(TMM_CHANNEL_ID_1_COMMAND)
            execute_tmm(TMM_CHANNEL_ID_2_COMMAND)
            await event.reply("TinyMediaManager ejecutado.")

    print("Bot de control iniciado. Esperando comandos...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
