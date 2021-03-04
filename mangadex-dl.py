#!/usr/bin/env python3
import cloudscraper
import time, os, sys, re, json, html, zipfile, argparse, shutil

A_VERSION = "0.5"

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
		r = scraper.get("https://api.mangadex.{}/v2/manga/{}/?include=chapters".format(tld, manga_id))
		jason = json.loads(r.text)
	except (json.decoder.JSONDecodeError, ValueError) as err:
		print("CloudFlare error: {}".format(err))
		exit(1)
	except:
		print("Error with URL.")
		exit(1)

	try:
		title = jason["data"]["manga"]["title"]
	except:
		print("Please enter a valid MangaDex manga (not chapter) URL or ID.")
		exit(1)
	print("\nTITLE: {}".format(html.unescape(title)))

	# check available chapters
	chapters = []
	for i in jason["data"]["chapters"]:
		if i["language"] == lang_code:
			chapters.append(i["chapter"])
	chapters.sort(key=float_conversion) # sort numerically by chapter #

	chapters = ["Oneshot" if x == "" else x for x in chapters]
	if len(chapters) == 0:
		print("No chapters available to download!")
		exit(0)
	else:
		print("Available chapters:")
		print(" " + ', '.join(map(str, chapters)))

	# i/o for chapters to download
	requested_chapters = []
	if input_chap == "":
		chap_list = input("\nEnter chapter(s) to download: ").strip()
	elif input_chap == "all":
		chap_list = "" + ','.join(map(str, chapters))
	elif input_chap == "last":
		chap_list = chapters[-1]
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
		elif s.lower() == "oneshot":
			if "Oneshot" in chapters:
				s = ["Oneshot"]
			else:
				print("Chapter {} does not exist. Skipping.".format(s))
		else:
			try:
				s = [chapters[chapters.index(s)]]
			except ValueError:
				print("Chapter {} does not exist. Skipping.".format(s))
				continue
		requested_chapters.extend(s)

	# find out which are availble to dl
	chaps_to_dl = []
	chapter_num = None
	for i in jason["data"]["chapters"]:
		try:
			chapter_num = str(float(i["chapter"]))
			chapter_num = re.sub('.0$', '', chapter_num) # only replace at end (not chapter #s with decimals)
		except: # oneshot
			if "Oneshot" in requested_chapters and i["language"] == lang_code:
				chaps_to_dl.append(("Oneshot", i["id"]))
		if chapter_num in requested_chapters and i["language"] == lang_code:
			chaps_to_dl.append((str(chapter_num), i["id"]))
	chaps_to_dl.sort(key = lambda x: float_conversion(x[0]))

	# get chapter(s) json
	print()
	for chapter_info in chaps_to_dl:
		print("Downloading chapter {}...".format(chapter_info[0]))
		r = scraper.get("https://api.mangadex.{}/v2/chapter/{}/".format(tld, chapter_info[1]))
		chapter = json.loads(r.text)

		# get url list
		images = []
		server = chapter["data"]["server"]
		if "mangadex." not in server:
			server = chapter["data"]["serverFallback"] # https://s2.mangadex.org/data/
		hashcode = chapter["data"]["hash"]
		volume = chapter["data"]["volume"]
		for page in chapter["data"]["pages"]:
			images.append("{}{}/{}".format(server, hashcode, page))

		# create combined group name
		groups = ""
		for i in range(len(chapter["data"]["groups"])):
			if i > 0:
				groups += " & "
			groups += chapter["data"]["groups"][i]["name"]
		groupname = re.sub('[/<>:"/\\|?*]', '-', groups)

		# download images
		for pagenum, url in enumerate(images, 1):
			filename = os.path.basename(url)
			ext = os.path.splitext(filename)[1]

			chapnum = zpad(chapter_info[0])
			volnum = ''
			if volume:
				volnum = 'v' + zpad(volume)
			if chapnum != "Oneshot":
				chapnum = 'c' + chapnum
				
			title = re.sub('[/<>:"/\\|?*]', '-', title)				
			subtitle = "{}{} [{}]".format(chapnum, volnum, groupname)

			dest_folder = os.path.join(os.getcwd(), "download", title, subtitle)
			if not os.path.exists(dest_folder):
				os.makedirs(dest_folder)
			dest_filename = pad_filename("{}{}".format(pagenum, ext))
			outfile = os.path.join(dest_folder, dest_filename)

			r = scraper.get(url)
			if r.status_code == 200:
				with open(outfile, 'wb') as f:
					f.write(r.content)
					print(" Downloaded page {}.".format(pagenum))
			else:
				# silently try again
				time.sleep(3)
				r = scraper.get(url)
				if r.status_code == 200:
					with open(outfile, 'wb') as f:
						f.write(r.content)
						print(" Downloaded page {}.".format(pagenum))
				else:
					print(" Skipping download of page {} - error {}.".format(pagenum, r.status_code))
			time.sleep(1)

		if zip_up == True:
			zip_name = os.path.join(os.getcwd(), "download", title, title + " " + subtitle + ".zip")
			chap_folder = os.path.join(os.getcwd(), "download", title, subtitle)
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
		parser.add_argument("--chapter", "-ch", default="last", help="Enter desired chapters, 'last' to download the latest chapter, or 'all' for all chapters.")

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
			url = input("Enter manga URL or ID: ").strip()

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
	except:
		print("Error with URL.")
		exit(1)

	dl(manga_id, lang_code, cbz_answer, url[-1], input_chap)
