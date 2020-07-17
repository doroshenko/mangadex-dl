#!/usr/bin/env python3
import cloudscraper
import time, os, sys, re, json, html, zipfile, argparse, shutil


A_VERSION = "0.3.1"

def pad_filename(str):
	digits = re.compile('(\\d+)')
	pos = digits.search(str)
	if pos:
		return str[1:pos.start()] + pos.group(1).zfill(3) + str[pos.end():]
	else:
		return str

def float_conversion(x):
	try:
		x = float(x)
	except ValueError: # empty string for oneshot
		x = 0
	return x

def zpad(num):
	if "." in num:
		parts = num.split('.')
		return "{}.{}".format(parts[0].zfill(3), parts[1])
	else:
		return num.zfill(3)

def dl(manga_id, lang_code, zip_up, tld="org", input_chap=""):
	# grab manga info json from api
	scraper = cloudscraper.create_scraper()
	try:
		r = scraper.get("https://mangadex.{}/api/manga/{}/".format(tld, manga_id))
		manga = json.loads(r.text)
	except (json.decoder.JSONDecodeError, ValueError) as err:
		print("CloudFlare error: {}".format(err))
		exit(1)

	try:
		title = manga["manga"]["title"]
	except:
		print("Please enter a MangaDex manga (not chapter) URL.")
		exit(1)
	print("\nTitle: {}".format(html.unescape(title)))

	# check available chapters
	chapters = []
	for chap in manga["chapter"]:
		if manga["chapter"][str(chap)]["lang_code"] == lang_code:
			chapters.append(manga["chapter"][str(chap)]["chapter"])
	chapters.sort(key=float_conversion) # sort numerically by chapter #

	chapters_revised = ["Oneshot" if x == "" else x for x in chapters]
	if len(chapters) == 0:
		print("No chapters available to download!")
		exit(0)
	else:
		print("Available chapters:")
		print(" " + ', '.join(map(str, chapters_revised)))

	# i/o for chapters to download
	requested_chapters = []
	if input_chap == "":
		chap_list = input("\nEnter chapter(s) to download: ").strip()
	elif input_chap == "last":
		chap_list = chapters_revised[-1]
	else:
		chap_list = input_chap
	chap_list = [s for s in chap_list.split(',')]
	for s in chap_list:
		s = s.strip()
		if "-" in s:
			split = s.split('-')
			lower_bound = split[0]
			upper_bound = split[1]
			try:
				lower_bound_i = chapters.index(lower_bound)
			except ValueError:
				print("Chapter {} does not exist. Skipping {}.".format(lower_bound, s))
				continue # go to next iteration of loop
			try:
				upper_bound_i = chapters.index(upper_bound)
			except ValueError:
				print("Chapter {} does not exist. Skipping {}.".format(upper_bound, s))
				continue
			s = chapters[lower_bound_i:upper_bound_i+1]
		else:
			try:
				s = [chapters[chapters.index(s)]]
			except ValueError:
				print("Chapter {} does not exist. Skipping.".format(s))
				continue
		requested_chapters.extend(s)

	# find out which are availble to dl
	chaps_to_dl = []
	for chapter_id in manga["chapter"]:
		try:
			chapter_num = str(float(manga["chapter"][str(chapter_id)]["chapter"])).replace(".0", "")
		except:
			pass # Oneshot
		chapter_group = manga["chapter"][chapter_id]["group_name"]
		if chapter_num in requested_chapters and manga["chapter"][chapter_id]["lang_code"] == lang_code:
			chaps_to_dl.append((str(chapter_num), chapter_id, chapter_group))
	chaps_to_dl.sort()

	# get chapter(s) json
	print()
	for chapter_id in chaps_to_dl:
		print("Downloading chapter {}...".format(chapter_id[0]))
		r = scraper.get("https://mangadex.{}/api/chapter/{}/".format(tld, chapter_id[1]))
		chapter = json.loads(r.text)

		# get url list
		images = []
		server = chapter["server"]
		if "mangadex." not in server:
			server = "https://mangadex.{}{}".format(tld, server)
		hashcode = chapter["hash"]
		for page in chapter["page_array"]:
			images.append("{}{}/{}".format(server, hashcode, page))

		# download images
		groupname = re.sub('[/<>:"/\\|?*]', '-', chapter_id[2])
		for pagenum, url in enumerate(images, 1):
			filename = os.path.basename(url)
			ext = os.path.splitext(filename)[1]

			title = re.sub('[/<>:"/\\|?*]', '-', title)
			dest_folder = os.path.join(os.getcwd(), "download", title, "c{} [{}]".format(zpad(chapter_id[0]), groupname))
			if not os.path.exists(dest_folder):
				os.makedirs(dest_folder)
			dest_filename = pad_filename("{}{}".format(pagenum, ext))
			outfile = os.path.join(dest_folder, dest_filename)

			for _ in range(0,10):
				try:
					r = scraper.get(url)
					if r.status_code == 200:
						with open(outfile, 'wb') as f:
							f.write(r.content)
				except:
					print("Encountered an error when downloading. Retrying...")
					time.sleep(2)
					continue
				break

			print(" Downloaded page {}.".format(pagenum))
			time.sleep(1)

		if zip_up == True:
			zip_name = os.path.join(os.getcwd(), "download", title, title + " c{} [{}]".format(zpad(chapter_id[0]), groupname))+".zip"
			chap_folder = os.path.join(os.getcwd(), "download", title, "c{} [{}]".format(zpad(chapter_id[0]), groupname))
			with zipfile.ZipFile(zip_name, 'w') as myzip:
				for root, dirs, files in os.walk(chap_folder):
					for file in files:
						myzip.write(os.path.join(root, file))

			print(" Chapter successfully packaged into .zip")
			
			shutil.rmtree(chap_folder)

	print("Done!")

if __name__ == "__main__":
	print("mangadex-dl v{}".format(A_VERSION))

	if len(sys.argv) > 1:
		parser = argparse.ArgumentParser()

		parser.add_argument("--url", "-u", default="", help="Enter Mangadex URL. Required.")
		parser.add_argument("--lang", "-l", default="gb", help="Set desired language (https://github.com/frozenpandaman/mangadex-dl/wiki/language-codes). Defaults to gb if left out.")
		parser.add_argument("--cbz", "-c", action="store_true", help="Include if you want to package chapter into .cbz")
		parser.add_argument("--chapter", "-ch", default="last", help="Enter desired chapters.")

		args = parser.parse_args()

		if args.url.strip() == "":
			print("You need to enter a URL")
			exit()
		if args.chapter.strip() == "":
			print("You need to enter chapter(s)")
			exit()
		url = args.url
		lang_code = args.lang
		cbz_answer = args.cbz
		input_chap = args.chapter

	else:
		url = ""
		while url == "":
			url = input("Enter manga URL: ").strip()

		cbz_answer = ""
		while cbz_answer == "":
			cbz_answer = input("Do you want to package chapters into .cbz?: (y/N) ").strip()
			if cbz_answer.lower() == "y":
				cbz_answer = True
			elif cbz_answer.lower() == "n" or cbz_answer == "":
				cbz_answer = False
			else:
				"Invalid input"
				cbz_answer = ""

		lang_code = ""
		while lang_code == "":
			lang_code = input("Enter desired language: (gb) ").strip()
			if lang_code == "":
				lang_code = "gb"

		input_chap=""

	try:
		manga_id = re.search("[0-9]+", url).group(0)
		split_url = url.split("/")
		for segment in split_url:
			if "mangadex" in segment:
				url = segment.split('.')
		dl(manga_id, lang_code, cbz_answer, url[1], input_chap)
	except Exception as e:
		print("Error: " + str(e))
