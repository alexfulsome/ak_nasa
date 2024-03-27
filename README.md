I forgot to ask but I assume you're running this on osx. Pretty sure it still doesn't come with git installed so unless you've used that before, the easiest way to download this is probably
1. download this as a .zip file (green 'code' button up top)
2. unpack it
3. open Terminal and type `cd ~/Downloads/xxx` where xxx is whatever name it unpacks as. Make sure you do the ~.

From what I saw in the screenshot you sent, you probably need to do 'python3' instead of 'python' every time. Do these in order in terminal (in that folder, after cd'ing):

1. `python3 -m venv nocuddles`
2. `source nocuddles/bin/activate`
3. `ROVER=curiosity CAMERA=RHAZ API_KEY=your_nasa_api_key python3 app.py`

ROVER can be any of them (all lowercase), CAMERA can be any of them (all upppercase). No spaces around the '='. 

It will make a photos/ directory and then a directory for each day/rover/camera combo like this: "photos/curiosity_RHAZ_2013-01-19/filename.JPG".

It will also write a file of all the urls for that day if you want to go pull them again later for some reason.

It has a rate limiting thing in there to keep you from going over your limit but you can change it. Limit is supposed to be 1000/hr but when I was testing it looks like your key might have 2k/hr? There's an explanation next to the relevant lines in app.py.

Avoided making you install any other packages but if you're getting network errors I might have to change a couple things and walk you through that.

Wrote it fast and only let it run for like 20 min so might be buggy. LMK
