# UNG-Script 1.0

UNG-Script is a simple language for building websites, with its own web server built in.
Everything is in one file, `ung.py`. All you need is Python 3.8 or newer, and nothing else has to be installed.

## Start in 3 steps

1. Put `ung.py` in a folder on your computer.
2. Open a terminal in that folder and make a starter website:
   ```
   python ung.py new mysite
   ```
3. Start the server:
   ```
   python ung.py serve mysite
   ```
   Then open **http://localhost:8000** in your browser.

To see the site on your phone, use the same WiFi and start the server with `--share`. It prints the address to open on the phone.

## What you get

| Address | What it is |
|---|---|
| `/` | Your home page (`index.ung`) |
| `/guestbook` | An example page that has a form and saves data |
| `/_guide` | The full guide in plain words, plus every built-in function |
| `/_playground` | Type code and run it straight away |

## A page looks like this

```
<ung>
name = "Sam"
fruits = ["mango", "banana"]
</ung>

<h1>Hello, {{ name }}!</h1>
<ung> for each fruit in fruits </ung>
  <li>{{ fruit }}</li>
<ung> end </ung>
```

- Plain HTML is shown as it is.
- Code goes between `<ung>` and `</ung>`.
- A value inside `{{ }}` is put into the page.

## Other commands

```
python ung.py run page.ung          run a file and print what it shows
python ung.py run page.ung name=Sam    ...as if a visitor typed name=Sam
python ung.py check page.ung        look for mistakes without running
python ung.py serve mysite --port 8080
```

## Good to know

- Files whose names start with `_` (like `_header.ung`) can be included by your pages, but visitors can't open them directly.
- Saved data goes into `_data.sqlite` in your site folder. Back up that file to keep your data.
- If a page has a mistake, the browser shows the problem in plain words, with the exact line highlighted.
