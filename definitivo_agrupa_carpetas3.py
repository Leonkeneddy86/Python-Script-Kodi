import os
import asyncio
import shutil
from telethon import TelegramClient, events, types
from telethon.errors import SessionPasswordNeededError

# Configuración
API_ID = ''
API_HASH = ''
PHONE_NUMBER = ''
SESSION_FILE = 'mi_sesion'

# IDs de los canales
CHANNEL_ID_1 = -1000000  # Canal 1 (Movies)
CHANNEL_ID_2 = -1000000  # Canal 2 (Series)
CONTROL_CHANNEL_ID = -10000000  # Canal de control

# Directorios para guardar y extraer archivos
SAVE_DIR_1 = '/home/deck/Downloads/Bot/Movies/.temp/'
SAVE_DIR_2 = '/home/deck/Downloads/Bot/Series/.temp/'
EXTRACT_DIR_1 = '/home/deck/Downloads/Bot/Movies/'
EXTRACT_DIR_2 = '/home/deck/Downloads/Bot/Series/'

# Mensajes configurables
MESSAGE_PROMPT_FOLDER = "Se detectó un grupo con ID `{grouped_id}`. ¿Quieres guardar los archivos en una carpeta nueva? Responde con `Y` o `N`."
MESSAGE_ENTER_FOLDER_NAME = "Por favor, introduce el nombre de la carpeta:"
MESSAGE_TIMEOUT_FOLDER = "No se recibió respuesta. Procediendo con la descarga y extracción."
MESSAGE_FOLDER_CREATED = "Carpeta `{folder_name}` creada exitosamente."
MESSAGE_PROCESS_COMPLETE = "Archivos del grupo `{grouped_id}` procesados y guardados en `{folder_path}`."
MESSAGE_NO_FILES_FOUND = "No se encontraron archivos en el grupo."

# Variables globales
is_running = False


async def process_grouped_files(client, message, save_dir, extract_dir):
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

    # Preguntar al usuario si desea crear una carpeta específica
    await client.send_message(message.chat_id, MESSAGE_PROMPT_FOLDER.format(grouped_id=grouped_id))

    # Esperar respuesta del usuario
    folder_name = None
    try:
        response_event = await wait_for_response(client, message.chat_id)
        if response_event.raw_text.strip().lower() == 'y':
            await client.send_message(message.chat_id, MESSAGE_ENTER_FOLDER_NAME)
            folder_name_event = await wait_for_response(client, message.chat_id)
            folder_name = folder_name_event.raw_text.strip()
            destination_folder = os.path.join(extract_dir, folder_name)
            os.makedirs(destination_folder, exist_ok=True)
            await client.send_message(message.chat_id, MESSAGE_FOLDER_CREATED.format(folder_name=folder_name))
        else:
            destination_folder = extract_dir

    except asyncio.TimeoutError:
        await client.send_message(message.chat_id, MESSAGE_TIMEOUT_FOLDER)
        destination_folder = extract_dir

    # Descargar y procesar los archivos del grupo
    file_paths = []
    for part in group_files:
        file_name = part.file.name if part.file else f"unknown_{part.id}"
        file_path = os.path.join(save_dir, file_name)
        file_paths.append(file_path)

        print(f"Descargando parte: {file_name}")
        await client.download_media(part, file_path)

    # Mover los archivos al destino final
    for file_path in file_paths:
        shutil.move(file_path, os.path.join(destination_folder, os.path.basename(file_path)))

    await client.send_message(
        message.chat_id,
        MESSAGE_PROCESS_COMPLETE.format(grouped_id=grouped_id, folder_path=destination_folder)
    )

    # Borrar todos los mensajes del grupo después de procesarlos
    for part in group_files:
        await delete_message(client, part)

    return max(msg.id for msg in group_files), True


async def wait_for_response(client, chat_id):
    """Esperar una respuesta del usuario en el chat."""
    loop = asyncio.get_event_loop()
    future_response = loop.create_future()

    async def response_handler(event):
        if event.chat_id == chat_id and not future_response.done():
            future_response.set_result(event)

    client.add_event_handler(response_handler, events.NewMessage(chats=chat_id))

    try:
        return await asyncio.wait_for(future_response, timeout=60)  # Tiempo límite de 60 segundos
    finally:
        client.remove_event_handler(response_handler)  # Eliminar el manejador al finalizar


async def process_single_file(client, message, save_dir, extract_dir):
    file_name = message.file.name if message.file else f"unknown_{message.id}"
    file_path = os.path.join(save_dir, file_name)

    print(f"Descargando: {file_name}")
    await client.download_media(message, file_path)

    dest_path = os.path.join(extract_dir, file_name)
    shutil.move(file_path, dest_path)

    print(f"Archivo movido: {dest_path}")

    # Borrar el mensaje original después de procesarlo
    await delete_message(client, message)

    return message.id, True


async def delete_message(client, message):
    try:
        await client.delete_messages(message.chat_id, [message.id])
        print(f"Mensaje borrado del canal: {message.id}")

    except Exception as e:
        print(f"Error al borrar el mensaje {message.id}: {str(e)}")


async def main_loop(client):
    global is_running

    last_message_id_1 = 0
    last_message_id_2 = 0

    while is_running:
        try:
            print("Esperando mensajes...")

            # Procesar canal 1 (Movies)
            last_message_id_1 = await process_channel(client,
                                                       CHANNEL_ID_1,
                                                       SAVE_DIR_1,
                                                       EXTRACT_DIR_1,
                                                       last_message_id_1)

            # Procesar canal 2 (Series)
            last_message_id_2 = await process_channel(client,
                                                       CHANNEL_ID_2,
                                                       SAVE_DIR_2,
                                                       EXTRACT_DIR_2,
                                                       last_message_id_2)

            print("Ciclo completado. Esperando...")
            await asyncio.sleep(15)

        except Exception as e:
            print(f"Error en el ciclo principal: {str(e)}")
            await asyncio.sleep(15)


async def process_channel(client, channel_id, save_dir, extract_dir, last_message_id):
    try:
        channel = await client.get_entity(channel_id)
        print(f"Procesando canal: {channel.title}")

        async for message in client.iter_messages(channel, min_id=last_message_id):
            if not is_running:
                break

            new_last_id, processed = await download_and_delete_media(client,
                                                                     message,
                                                                     save_dir,
                                                                     extract_dir)

            last_message_id = max(last_message_id, new_last_id)

        return last_message_id

    except Exception as e:
        print(f"Error al procesar el canal {channel_id}: {str(e)}")
        return last_message_id


async def download_and_delete_media(client, message, save_dir, extract_dir):
    if message.media:
        return await process_grouped_files(client, message, save_dir, extract_dir)

    else:
        print("El mensaje no contiene media.")

    return message.id, False


async def main():
    global is_running

    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()

    if not await client.is_user_authorized():
        await client.send_code_request(PHONE_NUMBER)
        try:
            await client.sign_in(PHONE_NUMBER, input('Introduce el código: '))
        except SessionPasswordNeededError:
            await client.sign_in(password=input('Introduce tu contraseña: '))

    @client.on(events.NewMessage(chats=CONTROL_CHANNEL_ID))
    async def command_handler(event):
        global is_running

        if event.raw_text == "/start":
            if not is_running:
                is_running = True
                asyncio.create_task(main_loop(client))  # Ejecutar en segundo plano
                await event.reply("Script iniciado.")
            else:
                await event.reply("El script ya está en ejecución.")

        elif event.raw_text == "/stop":
            if is_running:
                is_running = False
                await event.reply("Script detenido.")
            else:
                await event.reply("El script no está en ejecución.")

    print("Bot iniciado. Esperando comandos...")
    await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
