"""
MobbieLand — crooked Monopoly vs AI or hot-seat
Requires: pygame, numpy
"""

import json
import os
import time
import pygame
import random
import sys
import numpy as np

pygame.init()

MIN_W, MIN_H = 960, 640
DEFAULT_W, DEFAULT_H = 1280, 820
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".mobbieland.json")

win_state = {"w": DEFAULT_W, "h": DEFAULT_H, "x": None, "y": None}
_last_save_at = 0.0
SOUND_OK = False


def load_window_cfg():
    cfg = {"w": DEFAULT_W, "h": DEFAULT_H, "x": None, "y": None}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg["w"] = max(MIN_W, int(data.get("w", DEFAULT_W)))
        cfg["h"] = max(MIN_H, int(data.get("h", DEFAULT_H)))
        if data.get("x") is not None and data.get("y") is not None:
            cfg["x"] = int(data["x"])
            cfg["y"] = int(data["y"])
    except Exception:
        pass
    return cfg


def write_window_cfg(force=False):
    global _last_save_at
    now = time.time()
    if not force and now - _last_save_at < 0.25:
        return
    _last_save_at = now
    data = {
        "w": int(max(MIN_W, win_state["w"])),
        "h": int(max(MIN_H, win_state["h"])),
    }
    if win_state["x"] is not None and win_state["y"] is not None:
        data["x"] = int(win_state["x"])
        data["y"] = int(win_state["y"])
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


win_cfg = load_window_cfg()
win_state.update(win_cfg)
if win_cfg["x"] is not None and win_cfg["y"] is not None:
    if win_cfg["x"] > -20000 and win_cfg["y"] > -20000:
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{win_cfg['x']},{win_cfg['y']}"

W, H = win_cfg["w"], win_cfg["h"]
screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
pygame.display.set_caption("MobbieLand — Democracy is for sale, and so is lunch")
clock = pygame.time.Clock()

try:
    pygame.mixer.init(frequency=22050, size=-16, channels=2)
    SOUND_OK = True
except Exception:
    SOUND_OK = False

WINDOWMOVED = getattr(pygame, "WINDOWMOVED", None)
WINDOWSIZECHANGED = getattr(pygame, "WINDOWSIZECHANGED", None)

BG = (18, 22, 28)
PANEL = (28, 34, 44)
GOLD = (232, 184, 74)
WHITE = (240, 236, 228)
MUTED = (160, 168, 180)
RED = (220, 70, 70)
GREEN = (70, 190, 110)
BLUE = (80, 150, 230)
ORANGE = (230, 140, 50)
PURPLE = (170, 90, 210)
TEAL = (50, 190, 190)
PINK = (230, 110, 160)
JAIL = (90, 90, 110)
BLACK = (12, 12, 14)

FONT = pygame.font.SysFont("georgia", 17)
FONT_SM = pygame.font.SysFont("consolas", 13)
FONT_BIG = pygame.font.SysFont("georgia", 24, bold=True)
FONT_TINY = pygame.font.SysFont("consolas", 10)

START_CASH = 1500


def contrast_ink(rgb):
    r, g, b = rgb[:3]
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return BLACK if lum >= 0.58 else WHITE


def make_tone(freq, ms, vol=0.28, kind="sine"):
    if not SOUND_OK:
        return None
    try:
        sr = 22050
        n = max(1, int(sr * ms / 1000.0))
        t = np.arange(n, dtype=np.float32) / sr
        if kind == "square":
            wave = np.sign(np.sin(2 * np.pi * freq * t))
        else:
            wave = np.sin(2 * np.pi * freq * t)
        fade = min(400, max(1, n // 6))
        env = np.ones(n, dtype=np.float32)
        env[:fade] *= np.linspace(0, 1, fade)
        env[-fade:] *= np.linspace(1, 0, fade)
        wave = (wave * env * vol * 32767).astype(np.int16)
        stereo = np.ascontiguousarray(np.column_stack((wave, wave)))
        return pygame.sndarray.make_sound(stereo)
    except Exception:
        return None


def make_whoosh():
    if not SOUND_OK:
        return None
    try:
        sr = 22050
        n = int(sr * 0.12)
        t = np.linspace(0, 1, n)
        freq = 420 + 380 * t
        phase = np.cumsum(2 * np.pi * freq / sr)
        wave = (np.sin(phase) * (1 - t) * 0.22 * 32767).astype(np.int16)
        stereo = np.ascontiguousarray(np.column_stack((wave, wave)))
        return pygame.sndarray.make_sound(stereo)
    except Exception:
        return None


SFX = {}
if SOUND_OK:
    SFX = {
        "roll": make_tone(180, 70, 0.22, "square"),
        "step": make_whoosh(),
        "go": make_tone(523, 180, 0.25),
        "buy": make_tone(392, 140, 0.28),
        "rent": make_tone(220, 160, 0.26, "square"),
        "chance": make_tone(659, 120, 0.24),
        "jail": make_tone(110, 280, 0.3, "square"),
        "pol": make_tone(784, 200, 0.26),
        "extort": make_tone(311, 160, 0.28, "square"),
        "desert": make_tone(165, 240, 0.28),
        "club": make_tone(880, 90, 0.22),
        "doubles": make_tone(440, 80, 0.22),
        "lose_pol": make_tone(147, 220, 0.3, "square"),
        "bust": make_tone(98, 400, 0.32, "square"),
        "click": make_tone(700, 40, 0.16, "square"),
        "deny": make_tone(130, 120, 0.22, "square"),
        "gamble": make_tone(494, 90, 0.24, "square"),
        "police": make_tone(196, 200, 0.28, "square"),
    }


def sfx(name):
    snd = SFX.get(name)
    if snd:
        try:
            snd.play()
        except Exception:
            pass


def jokes(*lines):
    return list(lines)


J_HOTDOG = jokes(
    "The bun has a lobbyist in it.",
    "Mustard counts as a campaign color.",
    "Two dogs for the price of three. That's the brand.",
    "The cart wheels are registered PACs.",
    "Health rating: 'bold.'",
    "The onions are union. The ketchup is scab.",
    "You taste regulation and relish.",
    "A senator once cried into this relish tray.",
    "Free napkin if you look away during the transaction.",
    "The umbrella is a tax shelter.",
    "It snaps like a promise.",
)
J_PAYDAY = jokes(
    "APR so high it has its own zip code.",
    "They lend hope and repo the interest.",
    "Your dignity is collateral. Again.",
    "The pen is chained. So is the borrower.",
    "Same-day loan, same-decade regret.",
    "They smile like a repo man at a parade.",
    "Fine print is just print that knows jujitsu.",
    "You can pay weekly or spiritually.",
    "The mascot is a smiling anvil.",
    "Approval takes four seconds and your second born.",
)
J_INFLU = jokes(
    "Ring light brighter than your future.",
    "The closet has a ring light and no clothes.",
    "Engagement is up. Rent is also up.",
    "Sponsored by vibes and a credit card.",
    "The algorithm lives in the hamper.",
    "Three filters, zero permits.",
    "A brand deal fell behind the shoes.",
    "The mirror has a media kit.",
    "Followers can't cosign a mortgage. They tried.",
    "This hanger is a limited drop.",
)
J_CRYPTO = jokes(
    "The shed is on-chain and off-code.",
    "You HODL the padlock.",
    "Gas fees for the space heater.",
    "Whitepaper printed on a napkin.",
    "The whiteboard says WAGMI in fading marker.",
    "A raccoon understands the tokenomics better.",
    "Cold wallet, warm regrets.",
    "The generator runs on hopium.",
    "Utility: it exists. That's the pitch.",
    "Someone named the coin after their ex's dog.",
)
J_LAUNDRY = jokes(
    "Money goes in dirty and comes out... still damp.",
    "Cycle 4 is called 'plausible.'",
    "Lost socks and found invoices.",
    "The change machine launders change.",
    "Detergent smells like a subcommittee.",
    "Spin cycle doubles as a smear campaign.",
    "You folded a rumor into thirds.",
    "The attendant has seen your whites and your books.",
    "Express wash: 28 minutes, zero questions.",
    "A suit comes out with fewer ethics stains.",
)
J_CAR = jokes(
    "Every car has one previous owner: 'a guy.'",
    "The odometer only counts Tuesdays.",
    "Free pine tree, extra rust.",
    "Test drive includes a pep talk.",
    "The salesman could sell jail time.",
    "Warranty is a handshake in a wind tunnel.",
    "Check engine means check ego.",
    "Financing available in three moods.",
    "The lot floodlight is a character witness.",
    "Keys come with a story you shouldn't repeat.",
)
J_DRIVE = jokes(
    "The speaker box takes confessions.",
    "Combo 7 is a liability.",
    "Fries are a foreign policy.",
    "They upsell regret in a large cup.",
    "The drive-thru line is a filibuster.",
    "Secret menu: pay extra to forget.",
    "Napkins printed with NDAs.",
    "The mascot winked at a health inspector.",
    "Night shift runs on spite and soda.",
    "Your order number is also a bill number.",
)
J_BURGER = jokes(
    "The patty has a past.",
    "Pickles are unionized, lettuce is not.",
    "Special sauce is just confidence.",
    "Grill marks drawn on with a Sharpie of destiny.",
    "Kids meal toy: a tiny gavel.",
    "The bun filed for incorporation.",
    "You can taste the franchise agreement.",
    "One star, six secrets.",
    "The shake machine is 'down' in a spiritual sense.",
    "Manager's special is plausible deniability.",
)
J_PHARMA = jokes(
    "Side effects include owning the side effects.",
    "The lab coat has cufflinks.",
    "Clinical trial of your patience.",
    "Pills shaped like little loopholes.",
    "The poster says 'ask your lobbyist.'",
    "Expired? That's a rebrand.",
    "The beaker is full of quarterly guidance.",
    "You feel better and worse, on schedule.",
    "Patent pending on the smell.",
    "A rat in the maze unionized.",
)
J_BAR = jokes(
    "The stool remembers better than you will.",
    "Happy hour is a campaign event.",
    "Peanuts: complimentary. Secrets: market rate.",
    "The bartender is a constituent.",
    "Last call is a motion to adjourn.",
    "Neon sign flickers 'TRUST.'",
    "You tabbed a rumor.",
    "The jukebox only plays leverage.",
    "Ice cubes shaped like gavels.",
    "Bathroom graffiti is better policy.",
)
J_LIQUOR = jokes(
    "Aisle 3 is where morals go to ferment.",
    "The clerk knows your alibi brand.",
    "Two-for-one ethics.",
    "Brown bag of brown-bag ideas.",
    "ID check missed the soul.",
    "The lottery tickets are the chaser.",
    "Shelf talker: 'pairs well with hearings.'",
    "They sell hope in 750ml.",
    "The bell on the door is an alarm for dignity.",
    "Manager's key opens more than inventory.",
)
J_SOCIAL = jokes(
    "The lobby is a feed.",
    "Terms of service ate a senator.",
    "Downstairs is engagement. Upstairs is exile.",
    "The intern runs foreign policy by accident.",
    "Moderation team is a vending machine.",
    "You posted a building and it posted back.",
    "The cafeteria serves hot takes.",
    "Server farm, farmer none.",
    "Blue check on the fire extinguisher.",
    "The wifi password is 'consent.' It expired.",
)
J_MALL = jokes(
    "Fountain wishes go to corporate.",
    "Directory map includes 'your better judgment' as closed.",
    "Kiosk guy knows three laws and zero limits.",
    "Food court diplomacy fails at noon.",
    "Escalator to a higher deductible.",
    "Santa here is union and union-busting.",
    "The parking garage charges for memories.",
    "A mannequin dressed better than the board.",
    "Lost & found is a hedge fund.",
    "Closing time is a metaphor.",
)
J_PE = jokes(
    "They bought the company and sold the air.",
    "Synergies means fewer chairs.",
    "The pit is metaphorical until it isn't.",
    "Leverage so tall it needs FAA lights.",
    "Your job title is now 'optional.'",
    "They asset-stripped a vending machine.",
    "Spreadsheet with teeth.",
    "The ficus is fully depreciated.",
    "Partners don't shake hands. They vest.",
    "Exit strategy is the front door and a rumor.",
)
J_HOTEL = jokes(
    "Ice machine screams in C-minor.",
    "Towels thinner than the alibi.",
    "Magic fingers, tragic mattress.",
    "Vacancy sign flickers like a conscience.",
    "Room 12 has a guest who 'checked out.'",
    "Continental breakfast: a bun and a rumor.",
    "The Bible in the drawer is annotated.",
    "Hourly rates, daily regrets.",
    "Housekeeping knocked, then invoiced.",
    "You can see the parking lot and your choices.",
)
J_OIL = jokes(
    "It pumps crude and punchlines.",
    "The seagulls filed a brief.",
    "Hard hat, soft ethics.",
    "Spill kit includes a press release.",
    "The flame is eternal and off-books.",
    "A wrench named after a congressman.",
    "Safety third, dividends first.",
    "The ocean sent a complaint. It got tabled.",
    "You can smell GDP.",
    "Night shift talks to the derrick. It talks back.",
)
J_WH = jokes(
    "Velvet rope, iron invoices.",
    "The piano knows everyone's name and nobody's.",
    "Coat check takes coats and cover stories.",
    "Champagne is a character witness.",
    "The house rules are more like house suggestions.",
    "A politician left a cufflink and a speech.",
    "Red light means go, in this zip code.",
    "Tips accepted in cash, silence, and favors.",
    "The hallway carpet has heard appropriations bills.",
    "You didn't see anyone. They didn't see you. Invoice anyway.",
)
J_YACHT = jokes(
    "The yacht has a yacht.",
    "Zero-G, zero shame.",
    "Dock fees payable in moons.",
    "Captain's hat is a tax strategy.",
    "The lifeboat is branded.",
    "Stars look cheaper from here.",
    "A tender boat named 'Loophole.'",
    "You wave at regulations as they recede.",
    "Caviar with a side of jurisdiction.",
    "The horn plays a little fanfare for nobody.",
)
J_MOON = jokes(
    "Timeshare presentation lasts one lunar month.",
    "View of Earth, bill from orbit.",
    "Dust included. Air is an add-on.",
    "The brochure airbrushed the craters.",
    "Neighbors are rocks and one very lost probe.",
    "Low gravity, high HOA.",
    "You own 1/52nd of a regret.",
    "The gift shop sells bottled nothing.",
    "Night lasts two weeks. So does the pitch.",
    "Flag on the lawn is slightly used.",
)
J_THRONE = jokes(
    "The chair has a seating chart for reality.",
    "Gavel made of other gavels.",
    "Coffee is black. So is the budget.",
    "Nameplate says 'Acting Adult.'",
    "The window overlooks everyone else's problem.",
    "Minutes of the meeting: 'we won.'",
    "The intercom only hears yes.",
    "Cushions stuffed with old slogans.",
    "You sit. Markets flinch.",
    "A portrait blinks first.",
)
J_GAMBLE = jokes(
    "The chips are smiling. You shouldn't.",
    "Odds posted in disappearing ink.",
    "Dealer has a saint's patience and a devil's sleeve.",
    "A slot machine coughs up a button.",
    "VIP room is a closet with better lighting.",
    "House edge lives in the carpet pattern.",
    "You doubled down on a feeling.",
    "Cocktail waitress serves consequences.",
    "The dice know your credit score.",
    "Lucky socks, unlucky soul.",
)
J_JAIL = jokes(
    "The bars are ceremonial. The boredom isn't.",
    "Cellmate is writing a memoir called 'Almost.'",
    "Cafeteria meatloaf has a caucus.",
    "You get one phone call and it's a fundraiser.",
    "Orange is the new off-the-record.",
    "The rec yard is a networking event.",
    "Lights out, loopholes on.",
    "A guard asked for a selfie with your lawyer.",
    "Graffiti: 'was framed, still framed.'",
    "The cot squeaks in 4/4 time.",
)
J_VISIT = jokes(
    "Just visiting. That's what they all say.",
    "You brought muffins for the accused.",
    "The gift shop sells tiny bars of soap.",
    "A tourist took a photo. The inmate posed.",
    "Visiting hours include a brief crisis of faith.",
    "You wave. Someone files it under 'evidence of character.'",
    "The vending machine eats innocence.",
    "A kid asked if this is a museum of bad ideas.",
    "You signed in as 'fine, thanks.'",
    "The echo here has a publicist.",
)
J_PARK = jokes(
    "Free parking is the most expensive sentence on the board.",
    "A pigeon is running a valet.",
    "The meter is broken in your favor for once.",
    "You found a quarter and a subplot.",
    "Someone left a campaign flyer under the wiper.",
    "The space is free. The implication is not.",
    "You nap like a man with an alibi.",
    "A cop nods. That's the whole plot.",
    "Oil stain shaped like a state flower.",
    "You circle the lot of your life and stop here.",
)
J_POLICE = jokes(
    "The desk sergeant has seen every punchline.",
    "Badge polish is a line item.",
    "Two percent of your soul, payable now.",
    "The wanted poster blinked.",
    "Coffee here could prosecute.",
    "You get a receipt for your dignity.",
    "Holding cell has better Wi-Fi than home.",
    "A form in triplicate for 'just breathing.'",
    "The mascot is a stern German shepherd in a tie.",
    "They don't want a statement. They want a percentage.",
)
J_CLUB = jokes(
    "Bass so loud a bill passed.",
    "The VIP stamp is a committee assignment.",
    "Fog machine hiding three careers.",
    "DJ drops a beat and a name.",
    "Coat check mixed up two scandals.",
    "You danced with a budget amendment.",
    "Bottle service, zero service to the public.",
    "The bouncer collects anecdotes.",
    "Sunrise is a rumor here.",
    "A politician materialized near the subwoofer.",
)
J_DESERT = jokes(
    "Someone sold your secret for cab fare.",
    "The alley has ears and a rate card.",
    "A man in a hat already left with your guy.",
    "Informant fee: nature's tip jar.",
    "Loyalty lasted until the ATM.",
    "You hear heels. Then you hear a deposition.",
    "The dumpster is full of shredded yeses.",
    "A cat witnessed everything and wants hazard pay.",
    "Your politician left a note: 'new management.'",
    "The streetlight flickers like a conscience.",
)
J_CHANCE = jokes(
    "The card is thicker than the plot.",
    "Shuffle of fate, stacked a little.",
    "You drew a punchline with teeth.",
    "The deck has been in worse hands.",
    "Paper cut from destiny.",
    "This card smells like a press conference.",
    "Flip it. Flinch. File it.",
    "Luck is just spin with better lighting.",
    "The back of the card says 'no backsies.'",
    "You should have drawn the other one. There is no other one.",
)
J_EXTORT = jokes(
    "Smile. It's professional courtesy.",
    "The offer is optional like gravity.",
    "You brought a receipt for the shakedown.",
    "Business is booming and also ducking.",
    "A handshake with extra knuckles.",
    "You call it a partnership. They call it Tuesday.",
    "Protection from what? From you. That's the product.",
    "The clipboard makes it official.",
    "You invoice fear in neat rows.",
    "Nobody ran. That's respect or shin splints.",
)
J_GOTOJ = jokes(
    "Do not pass Go. Do not collect a speech.",
    "The cuffs are complimentary.",
    "A squad car with your name in the queue.",
    "You packed nothing and brought everything.",
    "The judge is on a snack break from you.",
    "Shortcut to reflection.",
    "Sirens in 3-part harmony.",
    "Your lawyer is already drafting a vibe.",
    "The sidewalk rolled up behind you.",
    "This ride has no aux cord.",
)
J_GO = jokes(
    "Salary of the damned: $200 and a wink.",
    "You circled the drain and got paid for it.",
    "GO is less a space than a lifestyle.",
    "Collect, deny, repeat.",
    "The bag was already yours. Now it's official.",
    "Start line, moral finish line TBD.",
    "A brass band of one cashier's check.",
    "You pass Go like a rumor passes a newsroom.",
    "The arrow points forward and slightly down.",
    "Another lap around the only joke in town.",
)
J_TAX = jokes(
    "Voluntary the way gravity is voluntary.",
    "The form has feelings.",
    "You paid. The receipt smirked.",
    "Bracket? You're in the 'oops' bracket.",
    "A penny saved is a penny audited.",
    "They taxed the poor in spirit too.",
    "Stamp says 'thanks for participating in society-ish.'",
    "Your accountant felt a disturbance.",
    "This is why cash hides in cakes.",
    "The IRS sent a fruit basket made of liens.",
)
J_BONUS = jokes(
    "A handshake in a hallway is a budget.",
    "You collected $50 and a rumor.",
    "Lobby Day: costumes encouraged.",
    "Name tag printed crooked on purpose.",
    "You mistook a senator for a coat rack. Both worked.",
    "Lanyard of destiny.",
    "The snack table is bipartisan dip.",
    "You got paid to nod.",
    "Someone mistook you for important. You invoiced.",
    "The banner fell. So did a standard.",
)
J_BUY_POL = jokes(
    "Aisle 1: principles. Aisle 2: people. You skip to 2.",
    "They're on sale if you don't make eye contact.",
    "Warranty void if used for good.",
    "The politician comes with a complimentary wave.",
    "You don't buy them. You subscribe.",
    "Gift wrapping is a flag pin.",
    "Returns accepted never.",
    "Bulk rate if you take the intern too.",
    "The price tag covers the soul surcharge.",
    "You hold the receipt up to the light. It winks.",
)
J_DICE = jokes(
    "Street dice don't take checks.",
    "The alley is the casino and the security.",
    "Someone rolled your luck down a drain.",
    "No owner. No refunds. No officer.",
    "A kid is the pit boss.",
    "The wall is padded with IOUs.",
    "You bet a little pride. It left town.",
    "Crap game, fancy metaphors.",
    "The coins come back slower than rumors.",
    "You cannot buy this corner. It already owns you.",
)

SPACES = [
    {"name": "GO — Grab the Bag", "type": "go", "jokes": J_GO},
    {"name": "Corner Hotdog Cart", "type": "prop", "price": 60, "rent": 8, "group": "slum", "color": (140, 90, 50), "jokes": J_HOTDOG},
    {"name": "Chance", "type": "chance", "jokes": J_CHANCE},
    {"name": "Payday Loan Shack", "type": "prop", "price": 80, "rent": 12, "group": "slum", "color": (140, 90, 50), "jokes": J_PAYDAY},
    {"name": "Night Club 'The Whip'", "type": "club", "jokes": J_CLUB},
    {"name": "Influencer Closet", "type": "prop", "price": 100, "rent": 16, "group": "hype", "color": PINK, "jokes": J_INFLU},
    {"name": "Extort a Business", "type": "extort", "jokes": J_EXTORT},
    {"name": "Crypto Shed", "type": "prop", "price": 120, "rent": 20, "group": "hype", "color": PINK, "jokes": J_CRYPTO},
    {"name": "24hr Laundry", "type": "prop", "price": 110, "rent": 18, "group": "wash", "color": (180, 180, 210), "jokes": J_LAUNDRY},
    {"name": "Burger Joint", "type": "prop", "price": 130, "rent": 22, "group": "food", "color": (180, 80, 40), "jokes": J_BURGER},
    {"name": "JAIL / Just Visiting", "type": "jail", "jokes": J_VISIT},
    {"name": "Used Car Lot", "type": "prop", "price": 140, "rent": 24, "group": "wheels", "color": ORANGE, "jokes": J_CAR},
    {"name": "Chance", "type": "chance", "jokes": J_CHANCE},
    {"name": "Drive-Thru Empire", "type": "prop", "price": 160, "rent": 28, "group": "wheels", "color": ORANGE, "jokes": J_DRIVE},
    {"name": "Tax the Poor ($100)", "type": "tax", "amount": 100, "jokes": J_TAX},
    {"name": "Pharma Bro Lab", "type": "prop", "price": 180, "rent": 32, "group": "pills", "color": RED, "jokes": J_PHARMA},
    {"name": "Buy a Politician", "type": "politician", "jokes": J_BUY_POL},
    {"name": "Informant Alley", "type": "desert", "jokes": J_DESERT},
    {"name": "The Last Call Bar", "type": "prop", "price": 170, "rent": 30, "group": "vice", "color": (120, 40, 70), "jokes": J_BAR},
    {"name": "Liquor Store", "type": "prop", "price": 190, "rent": 34, "group": "vice", "color": (120, 40, 70), "jokes": J_LIQUOR},
    {"name": "FREE PARKING", "type": "free", "jokes": J_PARK},
    {"name": "Social Media HQ", "type": "prop", "price": 200, "rent": 40, "group": "pills", "color": RED, "jokes": J_SOCIAL},
    {"name": "Chance", "type": "chance", "jokes": J_CHANCE},
    {"name": "Mega Mall of Despair", "type": "prop", "price": 220, "rent": 44, "group": "retail", "color": BLUE, "jokes": J_MALL},
    {"name": "Private Equity Pit", "type": "prop", "price": 240, "rent": 50, "group": "retail", "color": BLUE, "jokes": J_PE},
    {"name": "Extort a Business", "type": "extort", "jokes": J_EXTORT},
    {"name": "Night Club 'The Whip'", "type": "club", "jokes": J_CLUB},
    {"name": "Cheap Hotel", "type": "prop", "price": 210, "rent": 38, "group": "hospitality", "color": (90, 110, 140), "jokes": J_HOTEL},
    {"name": "Oil Rig of Feelings", "type": "prop", "price": 280, "rent": 60, "group": "oil", "color": (40, 40, 40), "jokes": J_OIL},
    {"name": "The Velvet Ledger", "type": "prop", "price": 260, "rent": 55, "group": "vice", "color": (120, 40, 70), "jokes": J_WH},
    {"name": "Street Dice Pit", "type": "gamble_fixed", "jokes": J_DICE},
    {"name": "GO TO JAIL", "type": "gotojail", "jokes": J_GOTOJ},
    {"name": "Space Yacht Dock", "type": "prop", "price": 320, "rent": 80, "group": "oil", "color": (40, 40, 40), "jokes": J_YACHT},
    {"name": "Chance", "type": "chance", "jokes": J_CHANCE},
    {"name": "Moon Timeshare", "type": "prop", "price": 350, "rent": 90, "group": "space", "color": TEAL, "jokes": J_MOON},
    {"name": "Police Station", "type": "police", "jokes": J_POLICE},
    {"name": "Golden Spoon Casino", "type": "prop", "price": 300, "rent": 70, "group": "gambling", "color": (160, 120, 40), "jokes": J_GAMBLE, "gamble": True},
    {"name": "Tax Shelter Audit ($150)", "type": "tax", "amount": 150, "jokes": J_TAX},
    {"name": "Boardroom Throne", "type": "prop", "price": 400, "rent": 120, "group": "space", "color": TEAL, "jokes": J_THRONE},
    {"name": "Lobby Day", "type": "bonus", "jokes": J_BONUS},
]

N = len(SPACES)
assert N == 40
JAIL_INDEX = next(i for i, s in enumerate(SPACES) if s["type"] == "jail")
SIDE = N // 4


def space_fill(s):
    if s["type"] == "prop":
        return s.get("color", (70, 78, 90))
    return {
        "go": GREEN, "chance": PURPLE, "jail": JAIL, "gotojail": RED,
        "tax": ORANGE, "free": TEAL, "politician": GOLD,
        "extort": PINK, "bonus": BLUE, "desert": (90, 70, 50),
        "club": (90, 30, 90), "police": (50, 70, 110),
        "gamble_fixed": (90, 70, 20),
    }.get(s["type"], (70, 78, 90))


def payday_mult(p):
    tiers = p.politicians // 6
    m = 1.0
    steps = (2.0, 2.0, 2.0, 2.0, 1.5, 1.25, 1.12, 1.06)
    for i in range(tiers):
        m *= steps[i] if i < len(steps) else 1.01
    return m


def fmt_mult(p):
    m = payday_mult(p)
    if abs(m - round(m)) < 1e-6:
        return str(int(round(m)))
    return f"{m:.2f}".rstrip("0").rstrip(".")


CHANCE_CARDS = [
    ("Health inspector raids every burger/hotdog you own. $45 each.", "tax_groups", {"food": 45, "slum": 20}),
    ("Your vice properties got too loud. Pay $50 per bar/liquor/velvet joint.", "tax_group", ("vice", 50)),
    ("Casino commission smells your gambling house. $80 if you own one.", "tax_group", ("gambling", 80)),
    ("Hotel towels were evidence. $60 per cheap hotel.", "tax_group", ("hospitality", 60)),
    ("Laundry machines ate a senator's sock. $40 per laundry.", "tax_group", ("wash", 40)),
    ("Recall on hype: pay $35 per influencer closet / crypto shed.", "tax_group", ("hype", 35)),
    ("Lemon law caravan. $40 per wheels property.", "tax_group", ("wheels", 40)),
    ("Pharma / social class-action. $55 each.", "tax_group", ("pills", 55)),
    ("Mall rats unionized. $50 per retail pit.", "tax_group", ("retail", 50)),
    ("Oil leak in the press. $70 per oil property.", "tax_group", ("oil", 70)),
    ("Space HOA assessment. $90 per space deed.", "tax_group", ("space", 90)),
    ("A senator clarifies the rules. Collect $150.", "cash", 150),
    ("Cousin is a regulator now. +1 politician.", "pol", 1),
    ("Viral apology tour. Pay $80 PR.", "pay", 80),
    ("You invent a convenience fee. Collect $100.", "cash", 100),
    ("Whistleblower. Pay $120 unless you own a politician.", "whistle", 120),
    ("Advance to GO and grab the bag.", "go", 0),
    ("Go directly to Jail. Dignity stays on the curb.", "jail", 0),
    ("Hostile takeover. Steal $75.", "steal", 75),
    ("Campaign refund glitch. Collect $200.", "cash", 200),
    ("Ethics nap. Free politician.", "pol", 1),
    ("EXTORTION LICENSE. Shake businesses like you landed on Extort.", "extort_card", 0),
    ("Blank check energy. Collect $90.", "cash", 90),
    ("Lobbyist outbid you. Pay $50.", "pay", 50),
    ("Masterclass. Next extort +50%.", "boost", 0),
    ("Someone loves your laundry. Collect $40 per wash property.", "pay_me_group", ("wash", 40)),
    ("Tourists flood the vice district. Collect $25 per vice deed.", "pay_me_group", ("vice", 25)),
]


class Player:
    def __init__(self, name, color, is_ai=False, short="P"):
        self.name = name
        self.short = short
        self.color = color
        self.is_ai = is_ai
        self.pos = 0
        self.draw_pos = 0.0
        self.cash = START_CASH
        self.props = []
        self.politicians = 0
        self.in_jail = False
        self.jail_turns = 0
        self.extort_boost = False
        self.bankrupt = False
        self.last_roll = (0, 0)
        self.doubles_streak = 0

    def add_cash(self, n):
        self.cash += int(n)

    def add_pol(self, n):
        self.politicians = max(0, self.politicians + n)

    def net_worth(self):
        worth = self.cash
        for i in self.props:
            worth += SPACES[i]["price"]
        worth += self.politicians * 150
        return max(0, worth)

    def group_count(self, group):
        return sum(1 for i in self.props if SPACES[i].get("group") == group)

    def group_total(self, group):
        return sum(1 for s in SPACES if s.get("group") == group)

    def has_monopoly(self, group):
        tot = self.group_total(group)
        return tot > 0 and self.group_count(group) == tot

    def rent_for(self, idx):
        s = SPACES[idx]
        rent = s["rent"]
        if self.has_monopoly(s["group"]):
            rent *= 2
        rent = int(rent * (1 + 0.15 * min(self.politicians, 8)))
        rent = int(rent * payday_mult(self))
        return rent

    def extort_charges(self):
        return 1 + (self.politicians // 2)


class Layout:
    def __init__(self, w, h):
        self.apply(w, h)

    def apply(self, w, h):
        self.w = max(MIN_W, w)
        self.h = max(MIN_H, h)
        panel_w = max(320, int(self.w * 0.34))
        margin = 16
        board_size = min(self.h - 2 * margin, self.w - panel_w - 3 * margin)
        self.board_rect = pygame.Rect(margin, (self.h - board_size) // 2, board_size, board_size)
        self.panel = pygame.Rect(self.board_rect.right + margin, margin, panel_w, self.h - 2 * margin)
        inset = board_size * 0.08
        inner_left = self.board_rect.left + inset
        inner_right = self.board_rect.right - inset
        inner_top = self.board_rect.top + inset
        inner_bottom = self.board_rect.bottom - inset
        span_x = inner_right - inner_left
        span_y = inner_bottom - inner_top
        step_x = span_x / SIDE
        step_y = span_y / SIDE
        gap = max(3, int(min(step_x, step_y) * 0.08))
        self.tile_w = max(36, int(step_x) - gap)
        self.tile_h = max(30, int(step_y) - gap)
        pts = []
        for i in range(SIDE):
            pts.append((int(inner_right - i * step_x), int(inner_bottom)))
        for i in range(SIDE):
            pts.append((int(inner_left), int(inner_bottom - i * step_y)))
        for i in range(SIDE):
            pts.append((int(inner_left + i * step_x), int(inner_top)))
        for i in range(SIDE):
            pts.append((int(inner_right), int(inner_top + i * step_y)))
        self.positions = pts[:N]
        self.tile_font = pygame.font.SysFont("consolas", max(8, min(13, self.tile_h // 5)))
        self.scale = board_size / 740.0
        pad = max(10, int(self.panel.w * 0.04))
        gap_x = max(6, int(self.panel.w * 0.02))
        self.btn_pad = pad
        self.btn_gap = gap_x
        self.btn_h1 = max(28, int(self.panel.h * 0.048))
        self.btn_h2 = max(26, int(self.panel.h * 0.042))
        self.btn_area_h = self.btn_h1 + self.btn_h2 + gap_x + pad
        fs = max(11, min(20, int(self.panel.w * 0.036)))
        self.btn_font = pygame.font.SysFont("georgia", fs)


layout = Layout(W, H)


class Game:
    def __init__(self):
        self.mode = None
        self.screen = "menu"
        self.reset_board()

    def reset_board(self, mode=None):
        self.mode = mode
        self.p1 = Player("Player 1 (Charming Menace)", BLUE, False, "P1")
        if mode == "hotseat":
            self.p2 = Player("Player 2 (Also Charming)", ORANGE, False, "P2")
        else:
            self.p2 = Player("The Algorithm", RED, True, "AI")
        self.you = self.p1
        self.ai = self.p2
        self.players = [self.p1, self.p2]
        self.turn = 0
        self.phase = "roll"
        self.dice = (0, 0)
        self.pending_buy = None
        self.winner = None
        self.extort_left = 0
        self.extort_mode = False
        self.moving = None
        self.ai_wait = 0
        self.ai_after_land = False
        self.keep_extort = False
        for s in SPACES:
            if s["type"] == "prop":
                s["owner"] = None
        if mode is None:
            self.screen = "menu"
            self.log = ["MobbieLand. Pick a fight: 1 vs Algorithm, 2 hot-seat."]
        else:
            self.screen = "play"
            vs = "hot-seat (two players)" if mode == "hotseat" else "Player 1 vs The Algorithm"
            self.log = [f"New game: {vs}. Morals optional."]

    def start_mode(self, mode):
        self.reset_board(mode)
        sfx("click")

    def rematch(self):
        if self.mode:
            self.reset_board(self.mode)
        else:
            self.reset_board(None)
        sfx("click")

    def log_msg(self, t):
        self.log.append(t)
        if len(self.log) > 18:
            self.log = self.log[-18:]

    def joke(self, space, extra=None):
        pool = extra if extra else space.get("jokes") or ["..."]
        self.log_msg("  " + random.choice(pool))

    def cur(self):
        return self.players[self.turn]

    def other(self, p):
        return self.p2 if p is self.p1 else self.p1

    def human_turn(self):
        return self.screen == "play" and not self.winner and not self.cur().is_ai and self.phase != "moving"

    def token_xy(self, p, pi):
        idx = p.draw_pos
        a = int(idx) % N
        b = (a + 1) % N
        t = idx - int(idx)
        x1, y1 = layout.positions[a]
        x2, y2 = layout.positions[b]
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        off = -10 if pi == 0 else 10
        return int(x + off), int(y + 6)

    def check_bust(self, p):
        if p.bankrupt:
            return True
        if p.cash <= 0 and p.politicians <= 0:
            p.cash = 0
            p.politicians = 0
            p.bankrupt = True
            sfx("bust")
            self.winner = self.other(p)
            self.screen = "over"
            self.log_msg(f"{p.name} is out of cash AND politicians. {self.winner.name} wins.")
            self.log_msg("Press R to rematch. Press 1 or 2 to pick a new mode.")
            return True
        return False

    def pay(self, p, n):
        n = int(max(0, n))
        p.cash -= n
        if p.cash < 0 and p.politicians > 0:
            while p.cash < 0 and p.politicians > 0:
                p.politicians -= 1
                p.cash += 80
                self.log_msg(f"{p.name} pawned a politician for $80 slush.")
                sfx("lose_pol")
        if p.cash < 0:
            p.cash = 0
        self.check_bust(p)

    def grant_cash(self, p, n):
        amt = int(n * payday_mult(p))
        p.add_cash(amt)
        return amt

    def teleport(self, p, idx, grant_go=False):
        p.pos = idx
        p.draw_pos = float(idx)
        if grant_go:
            got = self.grant_cash(p, 200)
            self.log_msg(f"{p.name} warped to GO and yoinked ${got}.")
            sfx("go")

    def send_to_jail(self, p):
        p.pos = JAIL_INDEX
        p.draw_pos = float(JAIL_INDEX)
        p.in_jail = True
        p.jail_turns = 0
        p.doubles_streak = 0
        sfx("jail")
        self.log_msg(f"{p.name} is in Jail.")
        self.joke({"jokes": J_JAIL})

    def steal(self, p, amt):
        o = self.other(p)
        take = min(int(amt * payday_mult(p)), max(0, o.cash))
        self.pay(o, take)
        p.add_cash(take)
        self.log_msg(f"{p.name} liberated ${take} from {o.name}.")

    def tax_group(self, p, group, per):
        n = p.group_count(group)
        if n <= 0:
            self.log_msg(f"  No {group} deeds. The fine shrugs and leaves.")
            return
        bill = n * per
        self.pay(p, bill)
        self.log_msg(f"  {n} {group} properties. Bill ${bill}.")

    def pay_me_group(self, p, group, per):
        n = p.group_count(group)
        if n <= 0:
            self.log_msg(f"  You own zero {group}. The payday walks past.")
            return
        got = self.grant_cash(p, n * per)
        self.log_msg(f"  {n} {group} deeds pay you ${got}.")

    def do_gamble(self, p, owned=False):
        sfx("gamble")
        if random.random() < 0.27:
            win = random.randint(12, 85)
            got = self.grant_cash(p, win)
            self.log_msg(f"{p.name} hit a lucky number. +${got}.")
        else:
            loss = random.randint(18, 95)
            if owned:
                loss = int(loss * 0.6)
            self.pay(p, loss)
            self.log_msg(f"{p.name} fed the house ${loss}. The house tipped its hat.")

    def land(self, p):
        if self.winner:
            return
        s = SPACES[p.pos]
        t = s["type"]
        self.pending_buy = None
        if t != "extort" and not getattr(self, "keep_extort", False):
            self.extort_left = 0
            self.extort_mode = False
        self.keep_extort = False
        self.joke(s)

        if t == "go":
            self.log_msg(f"{p.name} on GO.")
        elif t == "prop":
            owner = s.get("owner")
            if s.get("gamble") and owner is None:
                self.do_gamble(p, owned=False)
                self.pending_buy = p.pos
                self.log_msg(f"{s['name']} is unowned. Price ${s['price']}.")
            elif owner is None:
                self.pending_buy = p.pos
                self.log_msg(f"{s['name']} is unowned. Price ${s['price']}.")
            elif owner is p:
                self.log_msg(f"{p.name} visits their own {s['name']}.")
                if s.get("gamble"):
                    self.do_gamble(p, owned=True)
            else:
                rent = owner.rent_for(p.pos)
                discount = int(rent * 0.12 * min(p.politicians, 5))
                rent = max(5, rent - discount)
                self.pay(p, rent)
                owner.add_cash(rent)
                sfx("rent")
                self.log_msg(f"{p.name} pays ${rent} rent to {owner.name} for {s['name']}.")
                if s.get("gamble"):
                    self.do_gamble(p, owned=True)
        elif t == "gamble_fixed":
            self.log_msg("Street Dice cannot be bought. The alley already has an owner: chaos.")
            self.do_gamble(p, owned=False)
        elif t == "chance":
            self.draw_chance(p)
        elif t == "tax":
            self.pay(p, s["amount"])
            self.log_msg(f"{p.name} pays ${s['amount']} tax.")
        elif t == "jail":
            if p.in_jail:
                self.joke({"jokes": J_JAIL})
            else:
                self.log_msg(f"{p.name} is just visiting.")
        elif t == "free":
            got = self.grant_cash(p, 25)
            self.log_msg(f"Parking loophole +${got}.")
        elif t == "gotojail":
            self.send_to_jail(p)
        elif t == "bonus":
            got = self.grant_cash(p, 50)
            self.log_msg(f"Hallway handshake +${got}.")
        elif t == "politician":
            self.log_msg("A politician is $250 and a smile.")
        elif t == "extort":
            self.extort_left = p.extort_charges()
            self.log_msg(f"Extortion window: {self.extort_left} hit(s). Politicians stay.")
        elif t == "desert":
            sfx("desert")
            fee = self.grant_cash(p, 100)
            if p.politicians > 0:
                p.add_pol(-1)
                self.log_msg(f"A politician deserts. Informant fee ${fee}.")
                sfx("lose_pol")
            else:
                self.log_msg(f"Nobody left to desert. Still pocket ${fee}.")
        elif t == "club":
            p.add_pol(1)
            sfx("club")
            self.log_msg(f"{p.name} leaves The Whip with +1 politician.")
        elif t == "police":
            sfx("police")
            fee = max(1, int(p.net_worth() * 0.02))
            self.pay(p, fee)
            self.log_msg(f"Police Station surcharge: 2% of net worth = ${fee} to the bank.")

        self.check_bust(p)
        self.check_bust(self.other(p))

    def draw_chance(self, p):
        sfx("chance")
        text, kind, val = random.choice(CHANCE_CARDS)
        self.log_msg(f"CHANCE: {text}")
        if kind == "cash":
            got = self.grant_cash(p, val)
            self.log_msg(f"  Payday ${got}.")
        elif kind == "pay":
            self.pay(p, val)
        elif kind == "pol":
            p.add_pol(val)
            sfx("pol")
        elif kind == "whistle":
            if not p.politicians:
                self.pay(p, val)
            else:
                self.log_msg("  A politician yawned. File gone.")
        elif kind == "go":
            self.teleport(p, 0, grant_go=True)
        elif kind == "jail":
            self.send_to_jail(p)
        elif kind == "steal":
            self.steal(p, val)
        elif kind == "boost":
            p.extort_boost = True
        elif kind == "extort_card":
            self.extort_left = p.extort_charges()
            self.extort_mode = False
            self.keep_extort = True
            self.log_msg(f"  Paper says you can shake {self.extort_left} business(es) right now.")
        elif kind == "tax_group":
            self.tax_group(p, val[0], val[1])
        elif kind == "tax_groups":
            for gname, per in val.items():
                self.tax_group(p, gname, per)
        elif kind == "pay_me_group":
            self.pay_me_group(p, val[0], val[1])

    def start_move(self, p, steps):
        path = []
        pos = p.pos
        passed = 0
        for _ in range(steps):
            pos = (pos + 1) % N
            if pos == 0:
                passed += 1
            path.append(pos)
        self.moving = {"player": p, "path": path, "i": 0, "t": 0.0, "from": float(p.pos), "passed": passed}
        p.draw_pos = float(p.pos)
        self.phase = "moving"

    def update_move(self, dt):
        mv = self.moving
        if not mv:
            return
        p = mv["player"]
        mv["t"] += dt * 2.5
        dest = mv["path"][mv["i"]]
        start = mv["from"]
        if mv["t"] >= 1.0:
            mv["t"] = 0.0
            p.pos = dest
            p.draw_pos = float(dest)
            mv["from"] = float(dest)
            mv["i"] += 1
            sfx("step")
            if mv["i"] >= len(mv["path"]):
                if mv["passed"]:
                    for _ in range(mv["passed"]):
                        got = self.grant_cash(p, 200)
                        self.log_msg(f"{p.name} passed GO. +${got}.")
                        sfx("go")
                self.moving = None
                self.land(p)
                if not self.winner:
                    self.phase = "action"
                    if p.is_ai:
                        self.ai_after_land = True
                        self.ai_wait = 0.35
                return
        else:
            p.draw_pos = start + mv["t"]
            if p.draw_pos >= N:
                p.draw_pos -= N

    def jail_politician_tax(self, p):
        if p.politicians > 18:
            pct = random.randint(2, 7)
            lose = max(1, p.politicians * pct // 100)
            p.politicians -= lose
            sfx("lose_pol")
            self.log_msg(f"Overstaffed in jail: {p.name} loses {lose} politician(s) ({pct}%). No refund.")
            self.check_bust(p)

    def roll(self):
        p = self.cur()
        if p.bankrupt or self.winner or self.moving or self.screen != "play":
            return
        sfx("roll")
        d1, d2 = random.randint(1, 6), random.randint(1, 6)
        self.dice = (d1, d2)
        p.last_roll = self.dice
        doubles = d1 == d2

        if p.in_jail:
            self.jail_politician_tax(p)
            if self.winner:
                return

        if doubles:
            p.doubles_streak += 1
            sfx("doubles")
            self.log_msg(f"{p.name} rolled doubles ({d1}+{d2}). Streak {p.doubles_streak}.")
            if p.doubles_streak >= 3:
                p.doubles_streak = 0
                if p.politicians > 0:
                    p.add_pol(-1)
                    sfx("lose_pol")
                    self.log_msg("Three doubles. A politician walks.")
                self.check_bust(p)
        else:
            p.doubles_streak = 0

        if p.in_jail:
            if doubles:
                p.in_jail = False
                self.log_msg(f"{p.name} bribed the lock with doubles.")
                self.start_move(p, d1 + d2)
            else:
                p.jail_turns += 1
                if p.jail_turns >= 3:
                    self.pay(p, 50)
                    p.in_jail = False
                    self.log_msg(f"{p.name} paid $50 bail.")
                    if not self.winner:
                        self.start_move(p, d1 + d2)
                else:
                    self.log_msg(f"{p.name} failed jail break ({d1}+{d2}).")
                    self.phase = "end"
            return

        self.log_msg(f"{p.name} rolled {d1}+{d2}.")
        self.start_move(p, d1 + d2)

    def buy_property(self, p, idx=None):
        idx = self.pending_buy if idx is None else idx
        if idx is None:
            sfx("deny")
            return False
        s = SPACES[idx]
        if s["type"] != "prop" or s.get("owner") is not None:
            return False
        if p.cash < s["price"]:
            self.log_msg(f"{p.name} is too broke for {s['name']}.")
            sfx("deny")
            return False
        self.pay(p, s["price"])
        if self.winner:
            return False
        p.props.append(idx)
        s["owner"] = p
        self.pending_buy = None
        extra = " MONOPOLY!" if p.has_monopoly(s["group"]) else ""
        sfx("buy")
        self.log_msg(f"{p.name} bought {s['name']} for ${s['price']}.{extra}")
        return True

    def buy_politician(self, p):
        cost = 250
        if p.cash < cost:
            self.log_msg(f"{p.name} cannot afford a politician.")
            sfx("deny")
            return False
        self.pay(p, cost)
        if self.winner:
            return False
        p.add_pol(1)
        sfx("pol")
        extra = ""
        if p.politicians % 6 == 0 and p.politicians > 0:
            extra = f" Payday multiplier now x{fmt_mult(p)}!"
        self.log_msg(f"{p.name} bought a politician ({p.politicians} total).{extra}")
        return True

    def extort(self, p, target_idx):
        if self.extort_left <= 0:
            self.log_msg("No extortion charges left.")
            sfx("deny")
            return False
        s = SPACES[target_idx]
        if s["type"] != "prop":
            sfx("deny")
            return False
        owner = s.get("owner")
        if owner is p:
            self.log_msg("You cannot extort yourself.")
            sfx("deny")
            return False
        if owner is None:
            amt = 40
            if p.extort_boost:
                amt = int(amt * 1.5)
                p.extort_boost = False
            amt = int(amt * payday_mult(p))
            p.add_cash(amt)
            self.extort_left -= 1
            sfx("extort")
            self.log_msg(f"{p.name} extorted independent {s['name']} for ${amt}. ({self.extort_left} left)")
            return True
        base = max(30, s["rent"])
        if p.extort_boost:
            base = int(base * 1.5)
            p.extort_boost = False
        resist = int(base * 0.2 * min(owner.politicians, 4))
        amt = max(10, base - resist)
        amt = int(amt * payday_mult(p))
        self.pay(owner, amt)
        p.add_cash(amt)
        self.extort_left -= 1
        sfx("extort")
        self.log_msg(f"{p.name} extorted {owner.name}'s {s['name']} for ${amt}. ({self.extort_left} left)")
        return True

    def end_turn(self):
        if self.winner or self.moving or self.screen != "play":
            return
        self.pending_buy = None
        self.extort_left = 0
        self.extort_mode = False
        self.turn = 1 - self.turn
        self.phase = "roll"
        self.ai_after_land = False
        self.log_msg(f"— {self.cur().name}'s turn —")
        if self.cur().is_ai:
            self.ai_wait = 0.3

    def ai_act(self):
        p = self.cur()
        if not p.is_ai:
            return
        s = SPACES[p.pos]
        reserve = 120
        if p.cash >= 250 + reserve:
            buys = 1
            if p.cash > 900:
                buys = 2
            if p.cash > 1600:
                buys = 3
            for _ in range(buys):
                if p.cash >= 250 + reserve:
                    self.buy_politician(p)

        if self.pending_buy is not None:
            idx = self.pending_buy
            pr = SPACES[idx]
            want = False
            if pr["price"] <= 200 and p.cash - pr["price"] >= 280:
                want = True
            if p.group_count(pr["group"]) >= 1 and p.cash - pr["price"] >= 250:
                want = True
            if pr.get("gamble") and p.cash > 800:
                want = True
            if p.cash < pr["price"] + 200:
                want = False
            if want:
                self.buy_property(p)
            else:
                self.log_msg("The Algorithm saves cash to buy more people.")
                self.pending_buy = None

        if s["type"] == "politician" and p.cash >= 250:
            while p.cash >= 400:
                if not self.buy_politician(p):
                    break

        if self.extort_left > 0:
            while self.extort_left > 0 and not self.winner:
                if not self.ai_choose_extort(p):
                    break

        while p.cash >= 500 and not self.winner:
            if not self.buy_politician(p):
                break

    def ai_choose_extort(self, p):
        foe = self.other(p)
        candidates = []
        for i, sp in enumerate(SPACES):
            if sp["type"] != "prop" or sp.get("owner") is p:
                continue
            score = sp["rent"]
            if sp.get("owner") is foe:
                score += 80 + foe.politicians
            else:
                score += 10
            candidates.append((score, i))
        if not candidates:
            return False
        candidates.sort(reverse=True)
        return self.extort(p, candidates[0][1])


game = Game()


def wrap_words(text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if font.size(test)[0] > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def buttons():
    p = layout.panel
    pad = layout.btn_pad
    gap = layout.btn_gap
    inner_w = p.w - 2 * pad
    row1_h = layout.btn_h1
    row2_h = layout.btn_h2
    by2 = p.bottom - pad - row2_h
    by1 = by2 - gap - row1_h
    w1 = max(70, (inner_w - 2 * gap) // 3)
    w2 = max(100, (inner_w - gap) // 2)
    x0 = p.x + pad
    return {
        "roll": pygame.Rect(x0, by1, w1, row1_h),
        "buy": pygame.Rect(x0 + w1 + gap, by1, w1, row1_h),
        "end": pygame.Rect(x0 + 2 * (w1 + gap), by1, inner_w - 2 * (w1 + gap), row1_h),
        "pol": pygame.Rect(x0, by2, w2, row2_h),
        "ext": pygame.Rect(x0 + w2 + gap, by2, inner_w - w2 - gap, row2_h),
    }


def btn(rect, label, hot=True):
    col = (60, 90, 70) if hot else (50, 54, 62)
    pygame.draw.rect(screen, col, rect, border_radius=8)
    pygame.draw.rect(screen, GOLD if hot else MUTED, rect, 2, border_radius=8)
    font = layout.btn_font
    txt = font.render(label, True, WHITE)
    if txt.get_width() > rect.width - 8:
        smaller = pygame.font.SysFont("georgia", max(9, font.get_height() - 4))
        txt = smaller.render(label, True, WHITE)
    screen.blit(txt, txt.get_rect(center=rect.center))


def tile_rect(i):
    x, y = layout.positions[i]
    return pygame.Rect(x - layout.tile_w // 2, y - layout.tile_h // 2, layout.tile_w, layout.tile_h)


def owner_tag(owner):
    if owner is None:
        return "—"
    return owner.short


def draw_board():
    r = layout.board_rect
    pygame.draw.rect(screen, (24, 30, 38), r, border_radius=12)
    pygame.draw.rect(screen, GOLD, r, 3, border_radius=12)
    pad = int(max(layout.tile_w, layout.tile_h) * 1.15)
    inner = r.inflate(-2 * pad, -2 * pad)
    if inner.width > 40 and inner.height > 40:
        pygame.draw.rect(screen, (32, 48, 42), inner, border_radius=8)
        title = FONT_BIG.render("MobbieLand", True, GOLD)
        screen.blit(title, title.get_rect(center=(inner.centerx, inner.centery - 58)))
        if game.screen == "menu":
            lines = [
                "1  —  Player vs The Algorithm",
                "2  —  Two players (hot-seat)",
                "Esc  —  quit",
            ]
        elif game.screen == "over":
            lines = [
                f"{game.winner.name} WINS" if game.winner else "Game over",
                "R  —  rematch (same mode)",
                "1 / 2  —  new mode",
            ]
        else:
            d = game.dice
            lines = [
                "People first. Then property. Then lunch.",
                f"Dice: {d[0]} + {d[1]}" if d[0] else "Dice: —",
                "Street Dice unbuyable | Police 2% NW | R after win",
            ]
        for i, line in enumerate(lines):
            img = FONT.render(line, True, WHITE)
            screen.blit(img, img.get_rect(center=(inner.centerx, inner.centery - 12 + i * 26)))

    tf = layout.tile_font
    for i, s in enumerate(SPACES):
        col = space_fill(s)
        ink = contrast_ink(col)
        rect = tile_rect(i)
        pygame.draw.rect(screen, col, rect, border_radius=5)
        pygame.draw.rect(screen, ink, rect, 1, border_radius=5)
        lines = wrap_words(s["name"], tf, rect.width - 6)
        for li, line in enumerate(lines[:3]):
            t = tf.render(line, True, ink)
            screen.blit(t, (rect.x + 3, rect.y + 3 + li * (tf.get_height() + 1)))
        if s["type"] == "prop":
            t = tf.render(f"${s['price']} {owner_tag(s.get('owner'))}", True, ink)
            screen.blit(t, (rect.x + 3, rect.bottom - tf.get_height() - 2))

    if game.screen != "menu":
        for pi, p in enumerate(game.players):
            if p.bankrupt:
                continue
            x, y = game.token_xy(p, pi)
            pygame.draw.circle(screen, (0, 0, 0), (x + 1, y + 2), 10)
            pygame.draw.circle(screen, p.color, (x, y), 9)
            pygame.draw.circle(screen, WHITE, (x, y), 9, 2)


def draw_panel():
    p = layout.panel
    pygame.draw.rect(screen, PANEL, p, border_radius=12)
    pygame.draw.rect(screen, GOLD, p, 2, border_radius=12)
    y = p.y + 12
    screen.blit(FONT_BIG.render("Ledgers of Sin", True, GOLD), (p.x + 16, y))
    y += 34
    for pl in game.players:
        pygame.draw.rect(screen, pl.color, (p.x + 16, y, 12, 54), border_radius=3)
        turn = "  <<" if game.screen == "play" and pl is game.cur() else ""
        screen.blit(FONT.render(pl.name + turn, True, WHITE), (p.x + 36, y))
        info = f"${pl.cash}  props:{len(pl.props)}  pols:{pl.politicians}  x{fmt_mult(pl)}"
        screen.blit(FONT_SM.render(info, True, MUTED), (p.x + 36, y + 20))
        screen.blit(FONT_SM.render(f"NW:${pl.net_worth()}  doubles:{pl.doubles_streak}", True, MUTED), (p.x + 36, y + 36))
        if pl.in_jail:
            screen.blit(FONT_SM.render("IN JAIL", True, ORANGE), (p.right - 80, y))
        y += 60

    screen.blit(FONT.render("The Gossip Column", True, GOLD), (p.x + 16, y))
    y += 22
    max_w = p.w - 32
    log_bottom = p.bottom - layout.btn_area_h - 16
    for line in game.log:
        for c in wrap_words(line, FONT_SM, max_w):
            screen.blit(FONT_SM.render(c, True, WHITE), (p.x + 16, y))
            y += 14
        y += 2
        if y > log_bottom:
            break

    bs = buttons()
    human = game.human_turn()
    btn(bs["roll"], "ROLL", human and game.phase == "roll")
    btn(bs["buy"], "BUY DEED", human and game.phase == "action" and game.pending_buy is not None)
    btn(bs["end"], "END TURN", human and game.phase in ("action", "end"))
    btn(bs["pol"], "BUY POLITICIAN $250", human and game.phase == "action")
    can_ext = human and game.phase == "action" and game.extort_left > 0
    btn(bs["ext"], f"EXTORT x{game.extort_left}", can_ext)
    if game.winner:
        screen.blit(FONT.render(f"{game.winner.name} WINS  (R rematch)", True, GOLD), (p.x + 16, log_bottom - 22))


def space_at(pos):
    for i in range(N):
        if tile_rect(i).collidepoint(pos):
            return i
    return None


running = True
while running:
    dt = clock.tick(60) / 1000.0
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            write_window_cfg(force=True)
            running = False
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                write_window_cfg(force=True)
                running = False
            elif e.key == pygame.K_1:
                game.start_mode("ai")
            elif e.key == pygame.K_2:
                game.start_mode("hotseat")
            elif e.key in (pygame.K_r, pygame.K_R) and game.screen == "over":
                game.rematch()
        elif e.type == pygame.VIDEORESIZE:
            nw, nh = max(MIN_W, e.w), max(MIN_H, e.h)
            screen = pygame.display.set_mode((nw, nh), pygame.RESIZABLE)
            layout.apply(nw, nh)
            win_state["w"], win_state["h"] = nw, nh
            write_window_cfg()
        elif WINDOWMOVED is not None and e.type == WINDOWMOVED:
            win_state["x"] = int(getattr(e, "x", win_state["x"] or 0))
            win_state["y"] = int(getattr(e, "y", win_state["y"] or 0))
            write_window_cfg()
        elif WINDOWSIZECHANGED is not None and e.type == WINDOWSIZECHANGED:
            nw, nh = screen.get_size()
            layout.apply(nw, nh)
            win_state["w"], win_state["h"] = nw, nh
            write_window_cfg()
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and game.human_turn():
            mx, my = e.pos
            bs = buttons()
            p = game.cur()
            if bs["roll"].collidepoint(mx, my) and game.phase == "roll":
                sfx("click")
                game.roll()
            elif bs["buy"].collidepoint(mx, my) and game.phase == "action":
                game.buy_property(p)
            elif bs["end"].collidepoint(mx, my) and game.phase in ("action", "end"):
                sfx("click")
                game.end_turn()
            elif bs["pol"].collidepoint(mx, my) and game.phase == "action":
                game.buy_politician(p)
            elif bs["ext"].collidepoint(mx, my) and game.phase == "action" and game.extort_left > 0:
                game.extort_mode = True
                sfx("click")
                game.log_msg("Click a property tile to shake it down.")
            elif game.extort_mode and game.phase == "action":
                idx = space_at((mx, my))
                if idx is not None:
                    game.extort(p, idx)
                    if game.extort_left <= 0:
                        game.extort_mode = False

    if game.screen == "play" and game.moving:
        game.update_move(dt)

    if game.screen == "play" and not game.winner and game.cur().is_ai:
        if game.phase == "roll" and not game.moving:
            game.ai_wait -= dt
            if game.ai_wait <= 0:
                game.roll()
        elif game.phase == "action" and game.ai_after_land and not game.moving:
            game.ai_wait -= dt
            if game.ai_wait <= 0:
                game.ai_act()
                game.ai_after_land = False
                if not game.winner:
                    game.end_turn()
        elif game.phase == "end":
            game.ai_wait -= dt
            if game.ai_wait <= 0:
                game.end_turn()

    if game.screen == "play" and game.cur().is_ai and game.phase == "moving":
        game.ai_after_land = True
        game.ai_wait = 0.35

    screen.fill(BG)
    draw_board()
    draw_panel()
    pygame.display.flip()

write_window_cfg(force=True)
pygame.quit()
sys.exit()