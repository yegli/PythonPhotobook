import os
from datetime import datetime
import time
from tqdm import tqdm  # type: ignore
import shutil
from modules.convert import convert_heic_to_jpeg


def get_earliest_date(file_path):
    try:
        stat_info = os.stat(file_path)
        modified_time = stat_info.st_mtime
        created_time = getattr(stat_info, "st_birthtime", None)
        if created_time is None:
            created_time = stat_info.st_ctime
        earliest_time = min(modified_time, created_time)
        return datetime.fromtimestamp(earliest_time)
    except FileNotFoundError:
        print(f"File not found: {file_path}. Using fallback date.")
        return datetime.now()


def extract_date_from_filename(file_name):
    try:
        date_part = file_name.split('_')[0]
        return datetime.strptime(date_part, "%Y%m%d")
    except (ValueError, IndexError):
        return None


def process_and_assign_date(file_path, allow_update=True):
    file_name = os.path.basename(file_path)
    extracted_date = extract_date_from_filename(file_name)
    if not extracted_date:
        if allow_update:
            print(f"Unable to extract a valid date from the file name: {file_name}")
        return None
    if not allow_update:
        return extracted_date
    try:
        mod_time = time.mktime(extracted_date.timetuple())
        os.utime(file_path, (mod_time, mod_time))
        print(f"Assigned modification date {extracted_date.strftime('%Y-%m-%d')} to file: {file_path}")
        return extracted_date
    except Exception as e:
        print(f"Failed to update modification date for file: {file_path} | Error: {e}")
        return None


def get_destination_path(file_path, destination_directory, allow_update=True, dest_basename=None):
    earliest_time = get_earliest_date(file_path)
    if earliest_time.date() == datetime.now().date():
        extracted_date = process_and_assign_date(file_path, allow_update=allow_update)
        if extracted_date:
            earliest_time = extracted_date
        else:
            if allow_update:
                print(f"Using current date for sorting as no valid date was extracted: {file_path}")
            earliest_time = datetime.now()
    if earliest_time is None:
        if allow_update:
            print(f"Skipping file due to missing date metadata: {file_path}")
        return None

    year_month_folder = earliest_time.strftime('%Y%m_%B')
    date_folder = earliest_time.strftime('%Y-%m-%d')
    file_name = dest_basename or os.path.basename(file_path)
    return os.path.join(destination_directory, "Images", year_month_folder, date_folder, file_name)


def image_sorting(source_directory, destination_directory, IMAGE_EXTENSIONS, dry_run=False, convertor=False):
    unsorted_folder = os.path.join(destination_directory, "Unsorted_Files")
    os.makedirs(unsorted_folder, exist_ok=True)

    image_extensions = {ext.lower() for ext in IMAGE_EXTENSIONS}

    try:
        total_files = 0
        for root, _, files in os.walk(source_directory):
            for file in files:
                if file.startswith('.'):
                    continue

                src_path = os.path.join(root, file)
                ext = os.path.splitext(file)[1].lower()

                if ext in image_extensions:
                    dest_basename = os.path.basename(file)
                    if ext == ".heic" and convertor:
                        dest_basename = os.path.splitext(dest_basename)[0] + ".jpg"
                    dest_path = get_destination_path(
                        src_path,
                        destination_directory,
                        allow_update=False,
                        dest_basename=dest_basename,
                    )
                else:
                    dest_path = os.path.join(unsorted_folder, ext[1:].upper(), file)

                if dest_path and not os.path.exists(dest_path):
                    total_files += 1
    except Exception as e:
        print(f"Error calculating total files: {e}")
        total_files = 0

    if total_files == 0:
        print("No new files found to move.")
        return

    with tqdm(total=total_files, desc="Organizing files") as progress_bar:
        for root, _, files in os.walk(source_directory):
            for file in files:
                if file.startswith('.'):
                    continue

                src_path = os.path.join(root, file)

                try:
                    ext = os.path.splitext(file)[1].lower()

                    if file.lower().endswith('.heic') and convertor:
                        converted_path = convert_heic_to_jpeg(src_path)
                        if not converted_path:
                            tqdm.write(f"Conversion failed for file: {src_path}")
                            continue
                        tqdm.write(f"Converted {os.path.basename(src_path)} to {converted_path}")
                        src_path = converted_path

                    if ext in image_extensions:
                        dest_path = get_destination_path(src_path, destination_directory)
                    else:
                        dest_path = os.path.join(unsorted_folder, ext[1:].upper(), file)

                    if os.path.exists(dest_path):
                        tqdm.write(f"File already exists, skipping: {dest_path}")
                        continue

                    if dry_run:
                        tqdm.write(f"DRY RUN: Would copy {src_path} to {dest_path}")
                        progress_bar.update(1)
                    else:
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copy2(src_path, dest_path)
                        progress_bar.update(1)

                except FileNotFoundError:
                    tqdm.write(f"File not found, skipping: {src_path}")
                    continue
                except Exception as e:
                    tqdm.write(f"Error processing file {src_path}: {e}")
                    continue
