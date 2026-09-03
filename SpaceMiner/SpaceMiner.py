#!/usr/bin/env python3
"""Space Miner — infinite 2D space mining game."""

import math, random, hashlib, array, pickle, os
import pygame

WIDTH, HEIGHT = 1280, 720
PANEL_W = 300
VIEW_W = WIDTH - PANEL_W
FPS = 60
SAVE_PATH = "space_miner_save.pkl"
CHUNK, GEN_RADIUS = 2800, 2
G, SOFT = 22.0, 50.0
MINE_SEEK_R, MINE_SEEK_ACC, MINE_MAX_SPEED = 340, 210, 280
MINE_RESPAWN, MAX_MINES_PER_PLANET = 60.0, 3
MINE_WAVE_1, MINE_WAVE_2 = 120.0, 360.0
THRUST, TURN, DRAG, MAX_SPEED = 380, 3.4, 0.9992, 520
START_LIVES, MAX_LIVES, START_SCORE = 8, 12, 10_000_000
ASTEROID_MAX_SPEED, LABEL_DIST, PEAK_PRICE = 22, 280, 1.55
ORBIT_NUDGE, SYSTEM_RANGE = 14.0, 520
NAV_MAX_LEN, NAV_MIN_LEN = 70, 16
TRACTOR_RANGE, TRACTOR_ACC = MINE_SEEK_R * 0.5, 160
ENCOUNTER_WAIT, PIRATE_WAIT = 16.0, 11.0
PIRATE_ACC, PIRATE_MAX_SPEED = 170, 289
PIRATE_SHOT_RATE, PIRATE_SHOT_SPEED, PIRATE_DAMAGE = 0.85, 357, 2
PIRATE_HP = 10
COMPANION_OFFSET, TETHER_SWING = 55, 1.15
SAMPLE_RATE = 22050
RESURRECT_WINDOW = 60.0
SHOW_DWELL = 3.0
SCARE_MIN, SCARE_MAX = 5.0, 10.0
LIFE_VALUE = {8: 800, 9: 2000, 10: 3600, 11: 4800}

ELEMENTS = [
    ("H","Hydrogen"),("He","Helium"),("Li","Lithium"),("Be","Beryllium"),
    ("B","Boron"),("C","Carbon"),("N","Nitrogen"),("O","Oxygen"),
    ("F","Fluorine"),("Ne","Neon"),("Na","Sodium"),("Mg","Magnesium"),
    ("Al","Aluminum"),("Si","Silicon"),("P","Phosphorus"),("S","Sulfur"),
    ("Cl","Chlorine"),("Ar","Argon"),("K","Potassium"),("Ca","Calcium"),
    ("Sc","Scandium"),("Ti","Titanium"),("V","Vanadium"),("Cr","Chromium"),
    ("Mn","Manganese"),("Fe","Iron"),("Co","Cobalt"),("Ni","Nickel"),
    ("Cu","Copper"),("Zn","Zinc"),("Ga","Gallium"),("Ge","Germanium"),
    ("As","Arsenic"),("Se","Selenium"),("Br","Bromine"),("Kr","Krypton"),
    ("Rb","Rubidium"),("Sr","Strontium"),("Y","Yttrium"),("Zr","Zirconium"),
    ("Nb","Niobium"),("Mo","Molybdenum"),("Tc","Technetium"),("Ru","Ruthenium"),
    ("Rh","Rhodium"),("Pd","Palladium"),("Ag","Silver"),("Cd","Cadmium"),
    ("In","Indium"),("Sn","Tin"),("Sb","Antimony"),("Te","Tellurium"),
    ("I","Iodine"),("Xe","Xenon"),("Cs","Cesium"),("Ba","Barium"),
    ("La","Lanthanum"),("Ce","Cerium"),("Pr","Praseodymium"),("Nd","Neodymium"),
    ("Pm","Promethium"),("Sm","Samarium"),("Eu","Europium"),("Gd","Gadolinium"),
    ("Tb","Terbium"),("Dy","Dysprosium"),("Ho","Holmium"),("Er","Erbium"),
    ("Tm","Thulium"),("Yb","Ytterbium"),("Lu","Lutetium"),("Hf","Hafnium"),
    ("Ta","Tantalum"),("W","Tungsten"),("Re","Rhenium"),("Os","Osmium"),
    ("Ir","Iridium"),("Pt","Platinum"),("Au","Gold"),("Hg","Mercury"),
    ("Tl","Thallium"),("Pb","Lead"),("Bi","Bismuth"),("Po","Polonium"),
    ("At","Astatine"),("Rn","Radon"),("Fr","Francium"),("Ra","Radium"),
    ("Ac","Actinium"),("Th","Thorium"),("Pa","Protactinium"),("U","Uranium"),
    ("Np","Neptunium"),("Pu","Plutonium"),("Am","Americium"),("Cm","Curium"),
    ("Bk","Berkelium"),("Cf","Californium"),("Es","Einsteinium"),
    ("Fm","Fermium"),("Md","Mendelevium"),("No","Nobelium"),
    ("Lr","Lawrencium"),("Rf","Rutherfordium"),("Db","Dubnium"),
    ("Sg","Seaborgium"),("Bh","Bohrium"),("Hs","Hassium"),("Mt","Meitnerium"),
    ("Ds","Darmstadtium"),("Rg","Roentgenium"),("Cn","Copernicium"),
    ("Nh","Nihonium"),("Fl","Flerovium"),("Mc","Moscovium"),
    ("Lv","Livermorium"),("Ts","Tennessine"),("Og","Oganesson"),
]
ALL_SYMBOLS = [e[0] for e in ELEMENTS]
MASS_NUMBERS = [
    1,4,7,9,11,12,14,16,19,20,23,24,27,28,31,32,35,40,39,40,
    45,48,51,52,55,56,59,58,63,64,69,74,75,80,79,84,85,88,89,90,
    93,98,98,102,103,106,107,114,115,120,121,130,127,132,133,138,
    139,140,141,142,145,152,153,158,159,164,165,166,169,174,175,
    180,181,184,187,192,193,195,197,202,205,208,209,209,210,222,
    223,226,227,232,231,238,237,244,243,247,247,251,252,257,258,
    259,266,267,268,269,270,269,270,281,282,285,286,289,290,293,294,294,
]
ALKALI=["Li","Na","K","Rb","Cs","Fr"]
ALKALINE=["Be","Mg","Ca","Sr","Ba","Ra"]
TRANSITION=["Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn","Y","Zr","Nb","Mo","Tc","Ru","Rh","Pd","Ag","Cd","Hf","Ta","W","Re","Os","Ir","Pt","Au","Hg","Rf","Db","Sg","Bh","Hs","Cn"]
POST_TRANS=["Al","Ga","In","Sn","Tl","Pb","Bi","Po","Nh","Fl","Mc","Lv"]
METALLOIDS=["B","Si","Ge","As","Sb","Te","At"]
REACTIVE_NONMETALS=["H","C","N","O","F","P","S","Cl","Se","Br","I","Ts"]
NOBLE=["He","Ne","Ar","Kr","Xe","Rn","Og"]
LANTHANIDES=["La","Ce","Pr","Nd","Pm","Sm","Eu","Gd","Tb","Dy","Ho","Er","Tm","Yb","Lu"]
ACTINIDES=["Ac","Th","Pa","U","Np","Pu","Am","Cm","Bk","Cf","Es","Fm","Md","No","Lr"]
GASES=["H","He","N","O","F","Ne","Cl","Ar","Kr","Xe","Rn","Og"]
LIQUIDS=["Hg","Br","Ga","Cs","Fr"]
GROUP1=["H","Li","Na","K","Rb","Cs","Fr"]
GROUP17=["F","Cl","Br","I","At","Ts"]
GROUP13_16=["B","C","N","O","Al","Si","P","S","Ga","Ge","As","Se","In","Sn","Sb","Te","Tl","Pb","Bi","Po","Nh","Fl","Mc","Lv"]
DIATOMIC=["H","N","O","F","Cl","Br","I"]
RADIOACTIVE=["Tc","Pm","Po","At","Rn","Fr","Ra","Ac","Th","Pa","U","Np","Pu","Am","Cm","Bk","Cf","Es","Fm","Md","No","Lr","Rf","Db","Sg","Bh","Hs","Mt","Ds","Rg","Cn","Nh","Fl","Mc","Lv","Ts","Og"]
SYNTHETIC=[s for s,_ in ELEMENTS[94:]]
METALS=sorted(set(ALKALI+ALKALINE+TRANSITION+POST_TRANS+LANTHANIDES+ACTINIDES))
NONMETALS=sorted(set(REACTIVE_NONMETALS+NOBLE))
SOLIDS=[s for s,_ in ELEMENTS if s not in GASES and s not in ("Hg","Br")]
ELEMENT_GROUPS=[
    {"id":"alkali","name":"Alkali metals","blurb":"Soft, shiny, very reactive metals of Group 1.","symbols":ALKALI},
    {"id":"alkaline","name":"Alkaline earth metals","blurb":"Reactive shiny metals of Group 2.","symbols":ALKALINE},
    {"id":"transition","name":"Transition metals","blurb":"Hard shiny conductors from Groups 3-12.","symbols":TRANSITION},
    {"id":"post","name":"Post-transition metals","blurb":"Softer metals with lower melting points.","symbols":POST_TRANS},
    {"id":"metalloid","name":"Metalloids","blurb":"Neither fully metal nor nonmetal.","symbols":METALLOIDS},
    {"id":"react_nm","name":"Reactive nonmetals","blurb":"They gain or share electrons readily.","symbols":REACTIVE_NONMETALS},
    {"id":"noble","name":"Noble gases","blurb":"Unreactive colorless gases of Group 18.","symbols":NOBLE},
    {"id":"lanthanide","name":"Lanthanides","blurb":"Rare-earth inner-transition metals.","symbols":LANTHANIDES},
    {"id":"actinide","name":"Actinides","blurb":"Radioactive inner-transition metals.","symbols":ACTINIDES},
    {"id":"fblock","name":"Lanthanides and actinides","blurb":"The whole f-block.","symbols":LANTHANIDES+ACTINIDES},
    {"id":"gases","name":"Room-temperature gases","blurb":"Gases at room temperature.","symbols":GASES},
    {"id":"liquids","name":"Liquids and near-liquids","blurb":"Mercury, bromine, and near-melters.","symbols":LIQUIDS},
    {"id":"solids","name":"Solids","blurb":"Stable solids on the table.","symbols":SOLIDS},
    {"id":"g1","name":"Group 1","blurb":"One valence electron. Form +1 ions.","symbols":GROUP1},
    {"id":"g2","name":"Group 2","blurb":"Two valence electrons. Form +2 ions.","symbols":ALKALINE},
    {"id":"g3_12","name":"Groups 3-12","blurb":"Variable valence.","symbols":TRANSITION},
    {"id":"g13_16","name":"Groups 13-16","blurb":"Mixed metals, metalloids, nonmetals.","symbols":GROUP13_16},
    {"id":"g17","name":"Group 17","blurb":"Halogens. Form -1 ions.","symbols":GROUP17},
    {"id":"g18","name":"Group 18","blurb":"Noble gases. Stable.","symbols":NOBLE},
    {"id":"metals","name":"Metals","blurb":"The metal side of the table.","symbols":METALS},
    {"id":"nonmetals","name":"Nonmetals","blurb":"The nonmetal cut.","symbols":NONMETALS},
    {"id":"radio","name":"Radioactive elements","blurb":"Unstable nuclei.","symbols":RADIOACTIVE},
    {"id":"synthetic","name":"Synthetic elements","blurb":"Z 95 and above.","symbols":SYNTHETIC},
    {"id":"diatomic","name":"Diatomic elements","blurb":"They pair as two atoms.","symbols":DIATOMIC},
]
GEMS=[
    {"id":"diamond","name":"Diamond","color":(220,240,255),"shape":"diamond","price":3200,"lore":"Pressed in the throats of dead white dwarfs. Carbon that forgot how to burn."},
    {"id":"ruby","name":"Ruby","color":(210,30,50),"shape":"octagon","price":2800,"lore":"Chromium tears of a red giant, cooled in a pirate ballast tank."},
    {"id":"sapphire","name":"Sapphire","color":(40,80,210),"shape":"oval","price":2700,"lore":"Ice from a nitrogen ocean, stained by cobalt vents."},
    {"id":"emerald","name":"Emerald","color":(30,170,90),"shape":"rect","price":2600,"lore":"Grown in greenhouse asteroids to fool customs. Sometimes real."},
    {"id":"amethyst","name":"Amethyst","color":(150,70,200),"shape":"hex","price":2100,"lore":"Quartz that drank a purple nebula and never slept it off."},
    {"id":"topaz","name":"Topaz","color":(240,180,50),"shape":"diamond","price":2000,"lore":"Lightning glass from a storm-locked moon. Warm to the touch."},
    {"id":"opal","name":"Opal","color":(200,230,220),"shape":"oval","price":2400,"lore":"Frozen soap of a gas-giant ring. Plays every color it ever saw."},
    {"id":"garnet","name":"Garnet","color":(140,20,40),"shape":"hex","price":1900,"lore":"Blood rust of an iron world, cut after the war that made it."},
    {"id":"aquamarine","name":"Aquamarine","color":(70,200,210),"shape":"rect","price":1800,"lore":"Beryl pulled from a drowned station. Still smells like salt."},
    {"id":"citrine","name":"Citrine","color":(240,200,60),"shape":"triangle","price":1700,"lore":"Sunbaked quartz from a tide-locked desert. Cheap joy."},
    {"id":"peridot","name":"Peridot","color":(150,200,40),"shape":"octagon","price":1600,"lore":"Mantle chips coughed up by a baby volcano moon."},
    {"id":"onyx","name":"Onyx","color":(30,30,36),"shape":"rect","price":1500,"lore":"Night-glass poured in a smuggler foundry. Hides scratches well."},
    {"id":"pearl","name":"Pearl","color":(240,230,220),"shape":"circle","price":2200,"lore":"Grown by vacuum oysters around grit and guilt."},
    {"id":"turquoise","name":"Turquoise","color":(40,180,170),"shape":"oval","price":1600,"lore":"Copper veins meeting rain on a dry world. Desert sky in a rock."},
    {"id":"jade","name":"Jade","color":(50,150,90),"shape":"circle","price":1800,"lore":"Carved first as ballast idols. The lucky ones still hum."},
    {"id":"moonstone","name":"Moonstone","color":(200,210,230),"shape":"oval","price":2300,"lore":"Feldspar that remembered a moonrise and kept the glow."},
]
GEAR=[
    {"id":"lin_cap","name":"Linear Capacitor","color":(120,200,255),"cells":[(0,1),(1,1),(2,1),(3,1)],"price":2500,"lore":"A stick that stores grudges as charge. Do not lick the ends."},
    {"id":"core_cell","name":"Core Cell","color":(255,220,80),"cells":[(1,1),(2,1),(1,2),(2,2)],"price":2400,"lore":"Four bricks of bottled noon. Standard pirate lunch."},
    {"id":"tri_coup","name":"Tri-Coupler","color":(180,120,255),"cells":[(0,1),(1,1),(2,1),(1,2)],"price":2300,"lore":"Joins three bad ideas into one worse circuit."},
    {"id":"hook_act","name":"Hook Actuator","color":(255,150,60),"cells":[(0,0),(0,1),(0,2),(1,2)],"price":2200,"lore":"The arm that steals your tether when you look away."},
    {"id":"port_act","name":"Port Actuator","color":(80,180,255),"cells":[(1,0),(1,1),(1,2),(0,2)],"price":2200,"lore":"Left-handed twin of the Hook. Argues with it in the hold."},
    {"id":"skew_rel","name":"Skew Relay","color":(80,220,120),"cells":[(1,1),(2,1),(0,2),(1,2)],"price":2100,"lore":"Bends a signal until it admits it was lying."},
    {"id":"cskew","name":"Counter-Skew","color":(220,80,100),"cells":[(0,1),(1,1),(1,2),(2,2)],"price":2100,"lore":"Unbends the Skew Relay. They hate sharing a crate."},
    {"id":"dock_brk","name":"Docking Brick","color":(200,200,210),"cells":[(0,1),(1,1),(2,1)],"price":2000,"lore":"Three tiles that pretend to be a hatch. Sometimes they are."},
    {"id":"pulse_brk","name":"Pulse Brick","color":(255,90,90),"cells":[(1,0),(1,1),(1,2)],"price":2600,"lore":"A spine of strobe. Used to wake dead drives and neighbors."},
    {"id":"tether_w","name":"Tether Winch","color":(160,140,80),"cells":[(0,0),(1,0),(1,1),(1,2)],"price":2800,"lore":"Reels in companions, pirates, and regrets. Same setting."},
    {"id":"nav_brk","name":"Nav Brick","color":(90,220,220),"cells":[(0,1),(1,0),(1,1),(1,2)],"price":2700,"lore":"Knows where you are. Refuses to say unless paid in gems."},
    {"id":"shld_brk","name":"Shield Brick","color":(80,140,255),"cells":[(0,0),(1,0),(2,0),(1,1)],"price":3000,"lore":"A hat for a hull. Stops mines, not questions."},
]
LOOT_BY_ID={x["id"]:x for x in GEMS+GEAR}
GEM_IDS=[g["id"] for g in GEMS]
GEAR_IDS=[g["id"] for g in GEAR]
GUNS={
    None:None,
    "slow":{"rate":0.55,"spd":480,"dmg":1,"spread":0,"n":1,"life":1.6,"color":(255,230,120)},
    "mg":{"rate":0.08,"spd":620,"dmg":1,"spread":0.04,"n":1,"life":1.15,"color":(255,240,160)},
    "scatter":{"rate":0.42,"spd":500,"dmg":1,"spread":0.28,"n":5,"life":0.9,"color":(255,200,80)},
    "rail":{"rate":0.85,"spd":1100,"dmg":3,"spread":0,"n":1,"life":0.7,"color":(180,255,255)},
    "plasma":{"rate":0.32,"spd":420,"dmg":2,"spread":0.06,"n":1,"life":1.4,"color":(120,255,80)},
    "ion":{"rate":0.28,"spd":540,"dmg":2,"spread":0.02,"n":1,"life":1.3,"color":(80,180,255)},
    "flak":{"rate":0.38,"spd":460,"dmg":1,"spread":0.18,"n":3,"life":1.0,"color":(255,140,60)},
    "pulse":{"rate":0.22,"spd":580,"dmg":1,"spread":0,"n":2,"life":1.1,"color":(255,90,200)},
    "sweeper":{"rate":0.18,"spd":400,"dmg":2,"spread":0.12,"n":2,"life":1.5,"color":(200,255,140)},
    "beam":{"rate":0.05,"spd":900,"dmg":1,"spread":0.01,"n":1,"life":0.35,"color":(255,80,80)},
    "torpedo":{"rate":1.05,"spd":280,"dmg":5,"spread":0,"n":1,"life":2.4,"color":(255,160,40)},
    "drone":{"rate":0.5,"spd":360,"dmg":1,"spread":0.4,"n":3,"life":1.8,"color":(160,200,255)},
}

def build_aliens():
    kinds=(["robot"]*10+["siren"]*10+["mermaid"]*5+["humanoid"]*5+["insect"]*5+
           ["crustacean"]*5+["blob"]*4+["worm"]*3+["hair"]*3+["conjoined"]*5+
           ["triple"]*2+["crystal"]*5+["ghost"]*2+["xray"]*5+["fungal"]*4+
           ["avian"]*4+["cephalopod"]*4+["cactus"]*3+["moth"]*3+["slug"]*3+["mask"]*5)
    kinds=(kinds+["humanoid"]*20)[:100]
    names=["Orb-17","Vox-9","Click-Prime","Hex-Null","Aperture-3","Relay-K","Static-41","Beep-Row","Tape-II","Crown-Mech",
           "Lyssara","Vael","Serrin","Nimue","Calista","Ione","Mirael","Thale","Ysara","Phae",
           "Coral-Shen","Tide-Ryn","Aqualis","Brine-Sa","Pearl-Oth","Vesh-Ka","Ylla Varn","Dovik","Nohl","Peq",
           "Krrk","Mirrid Six","Lissid","Zai Zai","Hraa'n","Thul'Basa","Gratch","Brammek","Qorrun","Oom-Heth",
           "Urr-Vonn","Ixxen","Senee-Senee","Plooma","Glim-Tor","Ash-Fen","Dew-Kil","Fog-Ra","Stone-Eel","Last-Choir",
           "Twin-Vesh","Pair-Ool","Yoke-Sa","Hitch-Moth","Bind-Ra","Triune-Kel","Three-Well",
           "Quartz-Ith","Facet-9","Prism-Va","Shard-El","Lattice-Oo","Veil-Two","Glass-Fen",
           "See-Through","Organ-Song","Vein-Map","Gut-Light","Bone-Choir","Spore-Nel","Cap-Harbor","Mycel","Puff-Tithe",
           "Kite-Ra","Down-Well","Pinion","Sky-Scrip","Ink-Arm","Coil-Market","Suck-Ledger","Nine-Beak",
           "Needle-Sun","Bloom-Thorn","Dry-Well","Dust-Wing","Lamp-Moth","Ash-Scale",
           "Slow-Silver","Trail-Oil","Damp-Crown","False-Face","Second-Smile","Hollow-Guest","Mask-Broker","Lidless",
           "New-Tide","Old-Bridge","Far-Choir","Near-Market","Last-Note-II"]
    titles=[f"Factor {i+1}" for i in range(100)]
    skins=[(40+(i*37)%210,40+(i*19)%210,40+(i*53)%210) for i in range(100)]
    bgs=["techno","aquatic","floral","bridge","void"]
    weird=set(range(0,30))
    out=[]
    for i in range(100):
        kind=kinds[i]
        voice="humanoid"
        if kind=="robot": voice="teletype" if i<3 else "dtmf"
        elif kind=="mermaid": voice="mermaid"
        elif kind=="siren": voice="siren"
        elif kind in ("insect","hair","moth"): voice="chirp"
        elif kind=="crustacean": voice="click"
        elif kind=="crystal": voice="crystal"
        f0=72+i*9+(i*i%23)*4
        if kind=="crystal": f0=620+i*17
        if i in weird:
            eye_n=[1,2,3,6][i%4]; mixed=i%5==0
        else:
            eye_n=2; mixed=False
        head="box"
        if kind=="robot": head=["box","cylinder","oval"][i%3]
        coat=None
        if i%4==0: coat="fur"
        elif i%4==1 and i<50: coat="feather"
        out.append({
            "name":names[i],"title":titles[i],"skin":skins[i],
            "eye":(40+(i*17)%200,40+(i*29)%200,40+(i*13)%200),
            "f":f0,"kind":kind,"voice":voice,
            "want":"gear" if kind=="robot" else ("gem" if kind in ("siren","mermaid","hair","crystal") else None),
            "antenna":kind=="robot" and i%2==0,
            "spin360":i in (50,51,55,56,60),"trans_head":i in (50,51),
            "alpha":90 if kind=="xray" else (160 if kind=="ghost" or i in (50,51) else 255),
            "organs":kind=="xray",
            "bg":"aquatic" if kind in ("mermaid","cephalopod","slug") else bgs[i%len(bgs)],
            "eye_n":eye_n,"mixed_eyes":mixed,"big_eye":mixed or (i%9==0),
            "beak":kind in ("avian","moth") or i in (18,31),
            "dog":i in (12,26,4,7),"head":head,
            "fangs":i%5<2,"horns":i%5 in (0,1),
            "coat":coat if i%4 in (0,1) else None,
            "earrings":i in (10,12,14,16,21,23,3,9),
        })
    return out
ALIENS=build_aliens()

def element_family(z):
    if z in (1,6,7,8,15,16,34): return "Nonmetal"
    if z in (5,14,32,33,51,52): return "Metalloid"
    if z in (9,17,35,53,85,117): return "Halogen"
    if z in (2,10,18,36,54,86,118): return "Noble gas"
    if z in (3,11,19,37,55,87): return "Alkali metal"
    if z in (4,12,20,38,56,88): return "Alkaline earth metal"
    if 57<=z<=71: return "Lanthanide"
    if 89<=z<=103: return "Actinide"
    if z in (13,31,49,50,81,82,83,84,113,114,115,116): return "Post-transition metal"
    return "Transition metal"
FAMOUS={"H":(180,220,255),"He":(255,180,220),"C":(90,100,110),"O":(80,180,255),"Fe":(180,150,130),"Au":(255,205,60),"Ag":(220,230,235),"Pt":(200,215,225),"U":(90,180,90),"Cu":(205,120,60)}
def element_color(z,symbol):
    if symbol in FAMOUS: return FAMOUS[symbol]
    h=(z*0.37+z*z*0.013)%1.0; s,v=0.55+(z%5)*0.08,0.78+(z%3)*0.07
    i=int(h*6); f=h*6-i; p,q,t_=v*(1-s),v*(1-f*s),v*(1-(1-f)*s)
    r,g,b=[(v,t_,p),(q,v,p),(p,v,t_),(p,q,v),(t_,p,v),(v,p,q)][i%6]
    return int(r*255),int(g*255),int(b*255)
ELEMENT_INFO={}
for i,(sym,name) in enumerate(ELEMENTS,start=1):
    a=MASS_NUMBERS[i-1] if i-1<len(MASS_NUMBERS) else i*2
    ELEMENT_INFO[sym]={"symbol":sym,"name":name,"z":i,"a":a,"neutrons":a-i,"family":element_family(i),"color":element_color(i,sym),"base":80+(i*7)%820}

def build_help_pages():
    pages=[
        ["STORY","","A hundred contractors hail the dark between worlds.","Mine orbits, honor quotas, and keep the hull sealed.","Tractors only pull elements you have bought a beam for."],
        ["CONTROLS","","A/D rotate   W/Space thrust   S reverse   F fire","B / Tab  Chandlery     H / F1  this briefing","Y / Enter accept hail    N / Esc decline","F5 save    F9 load    ~ cheat console"],
        ["WARP","","Collect every machine part (12 gear types) to unlock warp.","Or type #warp in the ~ console.","Press G. Simulation pauses. Arrows scroll the map.","Enter, G, or Esc returns to the ship."],
        ["REINCARNATE","","Collect all 118 elements and all 16 jewels to earn RISE.","Or type #elements in the ~ console.","On GAME OVER a 60s clock starts.","Press Y before it dies to resurrect (>=3 lives).","R always starts a fresh run."],
        ["CHEATS  (~ then type a code, Enter)","","#immortal    cannot be hurt","#mortal      cancel immortality","#give        every store item + 10000c","#show        3s catalog of all aliens","#k           explode every pirate","#warp        grant warp map (G)","#elements    full catalog + rise"],
    ]
    titles={"STORY","CONTROLS","WARP","REINCARNATE","CHEATS  (~ then type a code, Enter)",
            "PERIODIC TABLE","ELEMENT GROUPS","JEWELS","EQUIPMENT"}
    rows=[]
    for sym,name in ELEMENTS:
        info=ELEMENT_INFO[sym]
        rows.append(f"{info['z']:3d}  {sym:<3}  n={info['neutrons']:<3}  {name}")
    for start in range(0,len(rows),20):
        pages.append(["PERIODIC TABLE","",f"Z   sym  neutrons   (page {start//20+1})",""]+rows[start:start+20])
    gpage=["ELEMENT GROUPS",""]
    for g in ELEMENT_GROUPS:
        gpage.append(f"{g['name']}: {g['blurb']}")
        gpage.append("  "+", ".join(g["symbols"][:18])+("..." if len(g["symbols"])>18 else ""))
    pages.append(gpage[:13]); pages.append(["ELEMENT GROUPS",""]+gpage[13:])
    jp=["JEWELS",""]
    for g in GEMS: jp.append(g["name"]+": "+g["lore"])
    pages.append(jp[:10]); pages.append(["JEWELS",""]+jp[10:])
    ep=["EQUIPMENT",""]
    for g in GEAR: ep.append(g["name"]+": "+g["lore"])
    pages.append(ep[:8]); pages.append(["EQUIPMENT",""]+ep[8:])
    return pages, titles
HELP_PAGES, HELP_TITLES = build_help_pages()

def short_name(name,limit=11): return name if len(name)<=limit else name[:limit-1]+"."
def chunk_rng(cx,cy,salt=0): return random.Random(int(hashlib.md5(f"{cx}:{cy}:{salt}".encode()).hexdigest()[:16],16))
def clamp(v,a,b): return a if v<a else b if v>b else v
def lerp_angle(a,b,k):
    d=(b-a+math.pi)%math.tau-math.pi
    return a+d*clamp(k,0.0,1.0)
def value_needed(lives): return None if lives>=MAX_LIVES else LIFE_VALUE.get(lives,6000)
def live_mine_count(p): return sum(1 for a in p.asteroids if a.mine)
def dist_point_seg(px,py,ax,ay,bx,by):
    vx,vy=bx-ax,by-ay; l2=vx*vx+vy*vy
    if l2<1e-6: return math.hypot(px-ax,py-ay)
    t=clamp(((px-ax)*vx+(py-ay)*vy)/l2,0.0,1.0)
    return math.hypot(px-(ax+t*vx),py-(ay+t*vy))
def tick_market(table,vel,dt):
    for k in table:
        vel[k]+=random.uniform(-0.28,0.28)*dt; vel[k]*=0.97
        table[k]=clamp(table[k]+vel[k]*dt,0.55,1.85)
def loot_spot_price(spec,lm,bonus=1.0): return max(200,int(spec["price"]*lm.get(spec["id"],1.0)*bonus))
def nearby_quotes(system_elems,drops,ship,market,loot_market):
    rows,seen=[],set()
    for sym in system_elems:
        if sym in seen: continue
        seen.add(sym); info=ELEMENT_INFO[sym]; mul=market.get(sym,1.0)
        rows.append({"label":f"{info['z']} {short_name(info['name'])}","color":info["color"],
                     "price":clamp(int(info["base"]*mul*ship.price_bonus),100,1500),
                     "peak":mul>=PEAK_PRICE,"mul":mul})
    near=sorted((d for d in drops if d.alive and math.hypot(d.x-ship.x,d.y-ship.y)<900),key=lambda d:math.hypot(d.x-ship.x,d.y-ship.y))
    for loot in near:
        lid=loot.spec["id"]
        if lid in seen: continue
        seen.add(lid); mul=loot_market.get(lid,1.0)
        rows.append({"label":short_name(loot.spec["name"],14),"color":loot.spec["color"],
                     "price":loot_spot_price(loot.spec,loot_market,ship.price_bonus),
                     "peak":mul>=PEAK_PRICE,"mul":mul})
    return rows[:5]

DTMF=[(697,1209),(697,1336),(697,1477),(770,1209),(770,1336),(770,1477),(852,1209),(852,1336),(852,1477),(941,1336)]
def _stereo(mono):
    out=array.array("h")
    for s in mono:
        v=int(max(-32767,min(32767,s))); out.append(v); out.append(v)
    return pygame.mixer.Sound(buffer=out)
def make_noise_rumble(ms=220,volume=0.22):
    n=int(SAMPLE_RATE*ms/1000.0); rng,mono,low=random.Random(7),[],0.0
    for i in range(n):
        low=low*0.97+(rng.random()*2-1)*0.03
        mono.append((low*2.2+math.sin(2*math.pi*55*i/SAMPLE_RATE)*0.45)*volume*32767)
    return _stereo(mono)
def make_warning(ms=180,volume=0.16):
    n=int(SAMPLE_RATE*ms/1000.0)
    return _stereo([(math.sin(2*math.pi*620*i/SAMPLE_RATE)*0.55)*math.sin(math.pi*i/max(1,n-1))*volume*32767 for i in range(n)])
def make_blip(freq,ms=70,volume=0.14):
    n=int(SAMPLE_RATE*ms/1000.0)
    return _stereo([math.sin(2*math.pi*freq*i/SAMPLE_RATE)*(1-i/max(1,n))*volume*32767 for i in range(n)])
def make_alien_voice(alien):
    voice,f0=alien["voice"],alien["f"]
    rng=random.Random(hash(alien["name"])&0xFFFFFFFF)
    if voice=="dtmf":
        seq=[DTMF[(hash(alien["name"])+k*3)%len(DTMF)] for k in range(5)]; mono=[]
        for lo,hi in seq:
            n_on=int(SAMPLE_RATE*0.16); n_off=int(SAMPLE_RATE*0.06)
            for i in range(n_on):
                tt=i/SAMPLE_RATE; env=min(1.0,i/200.0)*min(1.0,(n_on-i)/200.0)
                mono.append((math.sin(2*math.pi*lo*tt)+math.sin(2*math.pi*hi*tt))*0.5*env*0.28*32767)
            mono.extend([0.0]*n_off)
        n_stat=int(SAMPLE_RATE*0.22)
        for i in range(n_stat): mono.append((rng.random()*2-1)*0.12*32767*(1-i/n_stat))
        return _stereo(mono)
    if voice=="teletype":
        n=int(SAMPLE_RATE*0.9); mono=[]
        for i in range(n):
            tt=i/SAMPLE_RATE; click=1.0 if i%55<8 else 0.0
            beep=math.sin(2*math.pi*(f0+240)*tt) if int(tt*7)%3==0 else 0.0
            mono.append((click*(rng.random()*2-1)*0.55+beep*0.3)*0.22*32767)
        return _stereo(mono)
    n=int(SAMPLE_RATE*(1.15 if voice in ("mermaid","crystal") else 0.75)); mono=[]
    for i in range(n):
        tt=i/SAMPLE_RATE; vib=1+0.03*math.sin(2*math.pi*5.5*tt)
        env=0.3+0.7*abs(math.sin(math.pi*tt/max(0.01,n/SAMPLE_RATE)*4))
        if voice=="mermaid":
            glide=f0*0.8+40*math.sin(tt*1.6)+18*math.sin(tt*0.4)
            w=math.sin(2*math.pi*glide*vib*tt)+0.25*math.sin(2*math.pi*glide*2*tt)
        elif voice=="siren":
            glide=f0+30*math.sin(tt*3); w=math.sin(2*math.pi*glide*vib*tt)+0.3*math.sin(2*math.pi*glide*1.5*tt)
        elif voice=="crystal":
            glide=f0+80*math.sin(tt*4); w=math.sin(2*math.pi*glide*tt)+0.4*math.sin(2*math.pi*glide*2.02*tt)
        elif voice=="chirp":
            w=math.sin(2*math.pi*(f0*2+300*math.sin(tt*22))*tt); w*=1.0 if int(tt*16)%2==0 else 0.2
        elif voice=="click":
            w=((rng.random()*2-1)+math.sin(2*math.pi*1600*tt)*0.3) if int(tt*28)%6==0 else 0.0
        else:
            w=math.sin(2*math.pi*f0*vib*tt)+0.28*math.sin(2*math.pi*f0*1.6*vib*tt)+(rng.random()*2-1)*0.04
        mono.append(w*env*0.16*32767)
    return _stereo(mono)

class Planet:
    def __init__(self,x,y,radius,density,color,key,elements):
        self.x,self.y,self.r=x,y,radius; self.mass=math.pi*radius*radius*density
        self.color,self.key,self.elements,self.asteroids=color,key,elements,[]
class Asteroid:
    def __init__(self,x,y,vx,vy,symbol,parent,mine=False,orbit_r=100,ecc=0.0):
        self.x,self.y,self.vx,self.vy=x,y,vx,vy
        self.symbol,self.parent,self.mine=symbol,parent,mine
        info=ELEMENT_INFO.get(symbol,ELEMENT_INFO["Fe"])
        self.r=5+(3 if mine else 0)+(info["z"]%3)
        self.color=(220,50,40) if mine else info["color"]
        self.alive,self.orbit_r,self.ecc=True,orbit_r,ecc
        self.cw=1 if random.random()<0.5 else -1
        self.chasing,self.respawn_in=False,0.0
class Bullet:
    def __init__(self,x,y,vx,vy,hostile=False,dmg=1,life=1.2,color=None,r=4):
        self.x,self.y,self.vx,self.vy=x,y,vx,vy
        self.life,self.r,self.hostile,self.dmg=life,r,hostile,dmg
        self.color=color or ((255,80,80) if hostile else (255,230,120))
class Loot:
    def __init__(self,x,y,spec):
        self.x,self.y=x,y; self.vx,self.vy=random.uniform(-40,40),random.uniform(-40,40)
        self.spec,self.alive=spec,True
class Pirate:
    def __init__(self,x,y,partner=None,deadly=False,shielded=False):
        self.x,self.y,self.vx,self.vy=x,y,0.0,0.0
        self.r,self.hp=14,PIRATE_HP+(6 if shielded else 0)
        self.cd=random.uniform(0.2,0.8)
        self.flee,self.partner,self.deadly=False,partner,deadly
        self.shielded,self.was_shielded=shielded,shielded
        self.shield_hits=4 if shielded else 0
        self.gx,self.gy,self.lock_t=x,y,random.uniform(0.3,0.8)
class Ship:
    def __init__(self):
        self.x=self.y=self.vx=self.vy=0.0
        self.ang=-math.pi/2; self.tether_ang=self.ang+math.pi/2
        self.r,self.lives,self.score=12,START_LIVES,START_SCORE
        self.value_toward_life,self.invuln=0,0.0; self.thrusting=False
        self.shield,self.shield_hits,self.gun,self.fire_cd=False,0,None,0.0
        self.shield_r=18; self.tractors,self.engine_boost=set(),0
        self.magnet,self.price_bonus,self.quiet=False,1.0,False
        self.armor,self.regen,self.companion=False,0.0,False
        self.cargo_bonus=1.0; self.cloak=self.jammer=False
        self.purchases={}; self.immortal=self.warp=False
        self.found_elems,self.found_gems,self.found_gear=set(),set(),set()
        self.cx=self.cy=0.0
    @property
    def can_resurrect(self):
        return self.found_elems>=set(ALL_SYMBOLS) and self.found_gems>=set(GEM_IDS)

def companion_pos(ship):
    return (ship.x+math.cos(ship.tether_ang)*COMPANION_OFFSET, ship.y+math.sin(ship.tether_ang)*COMPANION_OFFSET)
def owned_count(ship,item_id):
    table={"life":ship.lives,"tractor":len(ship.tractors),"boost":ship.engine_boost,
           "shield":ship.shield_hits if ship.shield else 0,"wide_shield":max(0,ship.shield_r-18)//8,
           "companion":int(ship.companion),"magnet":int(ship.magnet),"broker":int(ship.price_bonus>1),
           "quiet":int(ship.quiet),"armor":int(ship.armor),"regen":int(bool(ship.regen)),
           "cargo_bay":int(ship.cargo_bonus>1),"cloak":int(ship.cloak),"jammer":int(ship.jammer)}
    if item_id.startswith("gun_") or item_id in GUNS:
        return 1 if ship.gun==item_id.replace("gun_","") else 0
    return table.get(item_id,ship.purchases.get(item_id,0))
def grant_chandlery(ship):
    ship.shield,ship.shield_hits,ship.shield_r=True,max(ship.shield_hits,24),42
    ship.gun="mg"; ship.tractors=set(ALL_SYMBOLS); ship.companion=True
    ship.engine_boost=max(ship.engine_boost,3)
    ship.magnet=ship.quiet=ship.armor=ship.cloak=ship.jammer=True
    ship.price_bonus=1.35; ship.regen=1.0; ship.cargo_bonus=1.4
    ship.lives=min(MAX_LIVES,max(ship.lives,10)); ship.score+=10000
    for it in STORE_ITEMS: ship.purchases[it["id"]]=ship.purchases.get(it["id"],0)+1
def grant_catalog(ship):
    ship.found_elems=set(ALL_SYMBOLS); ship.found_gems=set(GEM_IDS); ship.found_gear=set(GEAR_IDS); ship.warp=True
def park_on_orbit(a):
    p=a.parent; theta=random.random()*math.tau
    r_now=max(p.r+a.r+24,a.orbit_r*(1+a.ecc*math.cos(theta)))
    a.x,a.y=p.x+math.cos(theta)*r_now,p.y+math.sin(theta)*r_now
    speed=min(ASTEROID_MAX_SPEED,math.sqrt(max(12.0,G*p.mass/max(r_now,1)))*0.30)
    a.vx,a.vy=-math.sin(theta)*a.cw*speed,math.cos(theta)*a.cw*speed
    a.chasing,a.alive,a.respawn_in=False,True,0.0
def arm_respawn(a):
    a.alive,a.chasing,a.respawn_in,a.vx,a.vy=False,False,MINE_RESPAWN,0.0,0.0
def add_mine_to_planet(p):
    if live_mine_count(p)>=MAX_MINES_PER_PLANET: return
    kind=random.choice(p.elements) if p.elements else "Fe"
    ecc,orbit,theta=random.uniform(0.02,0.28),p.r+random.uniform(80,300),random.random()*math.tau
    r_now=orbit*(1+ecc*math.cos(theta)); cw=1 if random.random()<0.55 else -1
    speed=min(ASTEROID_MAX_SPEED,math.sqrt(max(12.0,G*p.mass/max(r_now,1)))*0.3)
    a=Asteroid(p.x+math.cos(theta)*r_now,p.y+math.sin(theta)*r_now,-math.sin(theta)*speed*cw,math.cos(theta)*speed*cw,kind,p,True,orbit,ecc)
    a.cw=cw; p.asteroids.append(a)
def reinforce_mines(planets,game_time,w1,w2):
    if game_time>=MINE_WAVE_1 and not w1:
        for p in planets.values():
            if live_mine_count(p)<MAX_MINES_PER_PLANET: add_mine_to_planet(p)
        w1=True
    if game_time>=MINE_WAVE_2 and not w2:
        for p in planets.values():
            if live_mine_count(p)<MAX_MINES_PER_PLANET: add_mine_to_planet(p)
        w2=True
    return w1,w2
def generate_chunk(cx,cy,planets_by_key):
    rng=chunk_rng(cx,cy)
    for _ in range(rng.randint(1,3)):
        px=cx*CHUNK+rng.uniform(180,CHUNK-180); py=cy*CHUNK+rng.uniform(180,CHUNK-180)
        key=(round(px/40),round(py/40))
        if key in planets_by_key: continue
        if any((p.x-px)**2+(p.y-py)**2<(p.r+280)**2 for p in planets_by_key.values()): continue
        hue=rng.random()
        color=(int(80+140*hue),int(70+100*(1-hue)+rng.randint(0,40)),int(90+120*abs(0.5-hue)))
        elems=[e[0] for e in rng.sample(ELEMENTS,5)]
        radius,density=rng.uniform(38,110),rng.uniform(0.6,2.4)
        p=Planet(px,py,radius,density,color,key,elems); placed=False
        for j in range(rng.randint(8,18)):
            ecc,orbit,theta=rng.uniform(0.02,0.28),radius+rng.uniform(70,320),rng.random()*math.tau
            r_now=orbit*(1+ecc*math.cos(theta)); cw=1 if rng.random()<0.55 else -1
            speed=min(ASTEROID_MAX_SPEED,math.sqrt(max(12.0,G*p.mass/max(r_now,1)))*rng.uniform(0.22,0.4))
            a=Asteroid(px+math.cos(theta)*r_now,py+math.sin(theta)*r_now,-math.sin(theta)*speed*cw,math.cos(theta)*speed*cw,rng.choice(elems),p,j==0,orbit,ecc)
            a.cw=cw; p.asteroids.append(a); placed=placed or a.mine
        if not placed: add_mine_to_planet(p)
        planets_by_key[key]=p
def gravity_from_planets(x,y,planets):
    ax=ay=0.0
    for p in planets:
        dx,dy=p.x-x,p.y-y; d2=dx*dx+dy*dy+SOFT*SOFT; inv=1.0/math.sqrt(d2); f=G*p.mass/d2
        ax+=dx*inv*f; ay+=dy*inv*f
    return ax,ay
def keep_in_orbit(a,dt):
    p=a.parent; dx,dy=a.x-p.x,a.y-p.y; dist=math.hypot(dx,dy)
    if dist<1: return
    nx,ny=dx/dist,dy/dist; tx,ty=-ny*a.cw,nx*a.cw
    target=max(p.r+a.r+20,a.orbit_r*(1+a.ecc*0.35*math.cos(math.atan2(dy,dx))))
    err=target-dist
    a.vx+=nx*err*0.35*dt*ORBIT_NUDGE; a.vy+=ny*err*0.35*dt*ORBIT_NUDGE
    want=min(ASTEROID_MAX_SPEED,math.sqrt(max(8.0,G*p.mass/max(dist,1)))*0.30)
    tv=a.vx*tx+a.vy*ty; a.vx+=tx*(want-tv)*1.8*dt; a.vy+=ty*(want-tv)*1.8*dt

STORE_ITEMS=[
    {"id":"shield","name":"Mine Shield","cost":50000,"desc":"Deflects mines. Shared with companion."},
    {"id":"shield_pack","name":"Shield Cells","cost":18000,"desc":"Add 8 shield hits."},
    {"id":"wide_shield","name":"Wide Envelope","cost":22000,"desc":"Grows the shield ring."},
    {"id":"gun_slow","name":"Ore Cannon","cost":20000,"desc":"Slow gun. Unlocks loot contracts."},
    {"id":"gun_mg","name":"Mine Repeater","cost":65000,"desc":"Fast shots."},
    {"id":"gun_scatter","name":"Scatter Fan","cost":28000,"desc":"Five-shot cone."},
    {"id":"gun_rail","name":"Rail Spike","cost":72000,"desc":"High damage lance."},
    {"id":"gun_plasma","name":"Plasma Bloom","cost":48000,"desc":"Fat green bolts."},
    {"id":"gun_ion","name":"Ion Needle","cost":44000,"desc":"Blue piercing shot."},
    {"id":"gun_flak","name":"Flak Nest","cost":36000,"desc":"Three short bursts."},
    {"id":"gun_pulse","name":"Twin Pulse","cost":39000,"desc":"Paired magenta pulses."},
    {"id":"gun_sweeper","name":"Mine Sweeper","cost":41000,"desc":"Wide slow cutters."},
    {"id":"gun_beam","name":"Hot Beam","cost":80000,"desc":"Near-continuous sting."},
    {"id":"gun_torpedo","name":"Ore Torpedo","cost":55000,"desc":"Slow, brutal."},
    {"id":"gun_drone","name":"Drone Pod","cost":46000,"desc":"Three wandering bolts."},
    {"id":"tractor","name":"Traction Beam","cost":5000,"desc":"Adds one element to the pull list."},
    {"id":"all_tractor","name":"Omni Beam","cost":90000,"desc":"Pull every element."},
    {"id":"companion","name":"Companion Hull","cost":80000,"desc":"Tethered ship."},
    {"id":"life","name":"Spare Hull","cost":12000,"desc":"One extra life."},
    {"id":"life_bank","name":"Life Bank","cost":40000,"desc":"Three lives at once."},
    {"id":"boost","name":"Afterburner","cost":15000,"desc":"Stronger thrust."},
    {"id":"magnet","name":"Cargo Magnet","cost":8000,"desc":"Wider pickup."},
    {"id":"broker","name":"Broker License","cost":25000,"desc":"+25% sale price."},
    {"id":"quote_amp","name":"Quote Amp","cost":30000,"desc":"+35% sale price."},
    {"id":"quiet","name":"Dark Coat","cost":22000,"desc":"Mines lock later."},
    {"id":"armor","name":"Ablative Plating","cost":16000,"desc":"Survive hard landings."},
    {"id":"regen","name":"Auto-Doc","cost":30000,"desc":"A life every 90s."},
    {"id":"cargo_bay","name":"Deep Hold","cost":14000,"desc":"Loot pickup radius +40%."},
    {"id":"cloak","name":"Ash Veil","cost":34000,"desc":"Pirates still hunt, but aim badly."},
    {"id":"jammer","name":"Fear Horn","cost":27000,"desc":"Pirate scare lasts longer."},
    {"id":"repair_drone","name":"Repair Mite","cost":19000,"desc":"Small i-frame refresh."},
    {"id":"nav_lamp","name":"Nav Lamp","cost":9000,"desc":"Cosmetic. Longer nav ticks."},
    {"id":"hull_forge","name":"Hull Forge","cost":24000,"desc":"Survive hard landings."},
    {"id":"silent_drive","name":"Silent Drive","cost":21000,"desc":"Quieter engine, same thrust."},
]
def apply_store_item(ship,item_id):
    if item_id=="shield": ship.shield,ship.shield_hits=True,8
    elif item_id=="shield_pack": ship.shield=True; ship.shield_hits+=8
    elif item_id=="wide_shield":
        ship.shield=True; ship.shield_r=min(56,ship.shield_r+8)
        if ship.shield_hits<=0: ship.shield_hits=4
    elif item_id.startswith("gun_"): ship.gun=item_id.replace("gun_","")
    elif item_id=="all_tractor": ship.tractors=set(ALL_SYMBOLS)
    elif item_id=="companion": ship.companion=True
    elif item_id=="life":
        if ship.lives>=MAX_LIVES: return False
        ship.lives+=1
    elif item_id=="life_bank": ship.lives=min(MAX_LIVES,ship.lives+3)
    elif item_id=="boost": ship.engine_boost+=1
    elif item_id=="magnet": ship.magnet=True
    elif item_id=="broker": ship.price_bonus=max(ship.price_bonus,1.25)
    elif item_id=="quote_amp": ship.price_bonus=max(ship.price_bonus,1.35)
    elif item_id=="quiet": ship.quiet=True
    elif item_id in ("armor","hull_forge"): ship.armor=True
    elif item_id=="regen": ship.regen=1.0
    elif item_id=="cargo_bay": ship.cargo_bonus=1.4
    elif item_id=="cloak": ship.cloak=True
    elif item_id=="jammer": ship.jammer=True
    elif item_id=="repair_drone": ship.invuln=max(ship.invuln,4.0)
    return True
def ship_state(ship):
    d={k:getattr(ship,k) for k in ("x","y","vx","vy","ang","tether_ang","lives","score","value_toward_life","shield","shield_hits","shield_r","gun","engine_boost","magnet","price_bonus","quiet","armor","regen","companion","cargo_bonus","purchases","immortal","warp","cloak","jammer")}
    d["tractors"]=sorted(ship.tractors); d["found_elems"]=sorted(ship.found_elems)
    d["found_gems"]=sorted(ship.found_gems); d["found_gear"]=sorted(ship.found_gear)
    return d
def apply_ship_state(ship,d):
    for k,v in d.items():
        if k in ("tractors","found_elems","found_gems","found_gear"): setattr(ship,k,set(v))
        elif k=="purchases": ship.purchases=dict(v or {})
        else: setattr(ship,k,v)
def save_game(path,ship,market,loot_market,game_time,w1,w2,mission):
    with open(path,"wb") as f:
        pickle.dump({"ship":ship_state(ship),"market":market,"loot_market":loot_market,"game_time":game_time,"wave1_done":w1,"wave2_done":w2,"mission":mission},f)
def load_game(path,ship,market,loot_market):
    with open(path,"rb") as f: data=pickle.load(f)
    apply_ship_state(ship,data["ship"]); market.update(data.get("market",{})); loot_market.update(data.get("loot_market",{}))
    return data.get("game_time",0.0),data.get("wave1_done",False),data.get("wave2_done",False),data.get("mission")
def world_to_screen(wx,wy,camx,camy): return wx-camx+VIEW_W/2, wy-camy+HEIGHT/2
def draw_starfield(surf,camx,camy):
    rng=random.Random(1)
    for i in range(180):
        layer=0.15+(i%3)*0.12
        sx=((rng.randrange(0,20000)-camx*layer)%VIEW_W); sy=((rng.randrange(0,20000)-camy*layer)%HEIGHT)
        c=40+(i%3)*50
        if 0<=int(sx)<VIEW_W and 0<=int(sy)<HEIGHT: surf.set_at((int(sx),int(sy)),(c,c,c+20))
def draw_ship_shape(surf,x,y,ang,color,scale=1.0):
    c,s=math.cos(ang),math.sin(ang)
    pts=[(x+c*16*scale,y+s*16*scale),(x+c*-10*scale-s*9*scale,y+s*-10*scale+c*9*scale),(x+c*-6*scale,y+s*-6*scale),(x+c*-10*scale+s*9*scale,y+s*-10*scale-c*9*scale)]
    pygame.draw.polygon(surf,color,pts); pygame.draw.polygon(surf,(40,40,60),pts,1)
def draw_arrow(surf,x0,y0,x1,y1,color,width=2):
    pygame.draw.line(surf,color,(x0,y0),(x1,y1),width)
    ang=math.atan2(y1-y0,x1-x0)
    pygame.draw.line(surf,color,(x1,y1),(x1-math.cos(ang-0.45)*8,y1-math.sin(ang-0.45)*8),width)
    pygame.draw.line(surf,color,(x1,y1),(x1-math.cos(ang+0.45)*8,y1-math.sin(ang+0.45)*8),width)
def draw_nav_graph(surf,ship,planets,camx,camy):
    ranked=sorted(((math.hypot(p.x-ship.x,p.y-ship.y)-p.r,p) for p in planets),key=lambda i:i[0])
    if not ranked or ranked[0][0]<SYSTEM_RANGE: return
    ox,oy=world_to_screen(ship.x+math.cos(ship.ang)*42,ship.y+math.sin(ship.ang)*42,camx,camy)
    far=max(max(t[0] for t in ranked[:3]),1.0); pal=[(120,220,255),(180,255,170),(255,210,120)]
    for i,(clearance,p) in enumerate(ranked[:3]):
        dx,dy=p.x-ship.x,p.y-ship.y; dist=math.hypot(dx,dy) or 1
        length=NAV_MIN_LEN+(1-clamp(clearance/(far*1.15),0,1))*(NAV_MAX_LEN-NAV_MIN_LEN)
        draw_arrow(surf,ox,oy,ox+dx/dist*length,oy+dy/dist*length,pal[i],2)
def poly(cx,cy,n,r,rot=0):
    return [(cx+math.cos(rot+i*math.tau/n)*r,cy+math.sin(rot+i*math.tau/n)*r) for i in range(n)]
def draw_gem_shape(surf,cx,cy,spec,scale):
    col,sh,r=spec["color"],spec.get("shape","circle"),9*scale
    if sh=="circle":
        pygame.draw.circle(surf,col,(int(cx),int(cy)),int(r))
    elif sh=="diamond":
        pygame.draw.polygon(surf,col,[(cx,cy-r),(cx+r*0.75,cy),(cx,cy+r),(cx-r*0.75,cy)])
    elif sh=="triangle":
        pygame.draw.polygon(surf,col,[(cx,cy-r),(cx+r,cy+r*0.7),(cx-r,cy+r*0.7)])
    elif sh in ("hex","octagon"):
        pygame.draw.polygon(surf,col,poly(cx,cy,6 if sh=="hex" else 8,r))
    elif sh=="oval":
        pygame.draw.ellipse(surf,col,(cx-r*0.7,cy-r,r*1.4,r*2))
    else:
        pygame.draw.rect(surf,col,(cx-r*0.8,cy-r*0.55,r*1.6,r*1.1))
def draw_gear_shape(surf,cx,cy,spec,scale):
    s=max(4,int(10*scale)); cells=spec["cells"]; xs,ys=[c[0] for c in cells],[c[1] for c in cells]
    ox=cx-(min(xs)+max(xs))*0.5*s; oy=cy-(min(ys)+max(ys))*0.5*s
    for gx,gy in cells: pygame.draw.rect(surf,spec["color"],(ox+gx*s,oy+gy*s,s-1,s-1))
def draw_element_shape(surf,cx,cy,info,scale,font):
    r=18*scale; pygame.draw.circle(surf,info["color"],(int(cx),int(cy)),int(r))
    label=font.render(info["symbol"],True,(20,20,28)); surf.blit(label,label.get_rect(center=(int(cx),int(cy))))
def draw_wanted_preview(surf,font,small,offer,cx,cy):
    pygame.draw.rect(surf,(12,18,28),(cx-100,cy-110,200,230),border_radius=8)
    pygame.draw.rect(surf,(160,200,180),(cx-100,cy-110,200,230),2,border_radius=8)
    if offer.get("kind")=="element":
        examples=offer.get("examples") or []; n=max(1,len(examples))
        for i,sym in enumerate(examples[:5]): draw_element_shape(surf,cx+(i-(n-1)/2)*34,cy-20,ELEMENT_INFO[sym],0.85,small)
        name=offer.get("group_name","Elements")
    elif offer.get("loot_id"):
        spec=LOOT_BY_ID[offer["loot_id"]]
        if spec.get("shape"): draw_gem_shape(surf,cx,cy-10,spec,6.0)
        else: draw_gear_shape(surf,cx,cy-10,spec,3.2)
        name=spec["name"]
    else: name="Catalog"
    cap=small.render(name[:22],True,(230,240,255)); surf.blit(cap,cap.get_rect(center=(cx,cy+88)))
def draw_loot_item(surf,loot,camx,camy):
    sx,sy=world_to_screen(loot.x,loot.y,camx,camy)
    if loot.spec.get("shape"): draw_gem_shape(surf,sx,sy,loot.spec,1.0)
    else: draw_gear_shape(surf,sx,sy,loot.spec,0.55)
def draw_eye_set(surf,cx,cy,alien,t):
    n=alien.get("eye_n",2)
    if n<=0: return
    spots=[]
    if n==1: spots=[(0,-16,16 if alien.get("big_eye") else 8)]
    elif n==2:
        if alien.get("mixed_eyes"): spots=[(-18,-16,6),(20,-14,14)]
        else:
            r=14 if alien.get("big_eye") else 8
            spots=[(-18,-16,r),(18,-16,r)]
    elif n==3: spots=[(-22,-12,7),(0,-20,10),(22,-12,7)]
    else:
        for k in range(n):
            ang=-math.pi*0.8+k*(math.pi*1.6/max(1,n-1))
            spots.append((math.cos(ang)*26,-16+math.sin(ang)*8,6+(k==0)*6))
    for ox,oy,r in spots:
        pygame.draw.circle(surf,(250,250,250),(int(cx+ox),int(cy+oy)),int(r))
        pygame.draw.circle(surf,(20,20,24),(int(cx+ox+2*math.sin(t*0.9)),int(cy+oy)),max(2,int(r)-4))
def draw_horns(surf,cx,cy,skin):
    pygame.draw.polygon(surf,skin,[(cx-22,cy-50),(cx-34,cy-88),(cx-10,cy-52)])
    pygame.draw.polygon(surf,skin,[(cx+22,cy-50),(cx+34,cy-88),(cx+10,cy-52)])
def draw_fangs(surf,cx,cy):
    pygame.draw.polygon(surf,(240,240,245),[(cx-8,cy+14),(cx-4,cy+26),(cx-2,cy+14)])
    pygame.draw.polygon(surf,(240,240,245),[(cx+8,cy+14),(cx+4,cy+26),(cx+2,cy+14)])
def draw_coat(surf,cx,cy,kind):
    col=(160,120,80) if kind=="fur" else (180,200,220)
    for i in range(12):
        ang=-2.2+i*0.35
        pygame.draw.line(surf,col,(cx+math.cos(ang)*30,cy+math.sin(ang)*40),(cx+math.cos(ang)*42,cy+math.sin(ang)*54),2)
def draw_dog_mouth(surf,cx,cy,talking):
    open_amt=10 if talking else 3
    pygame.draw.ellipse(surf,(40,24,20),(cx-16,cy+8,32,18+open_amt)); draw_fangs(surf,cx,cy)
def head_offset(alien,t):
    if alien.get("spin360"): return 18*math.cos(t*0.7),10*math.sin(t*0.7)
    return 8*math.sin(t*0.55),5*math.sin(t*0.37+0.4)
def draw_organs(surf,cx,cy):
    pygame.draw.ellipse(surf,(180,40,50),(cx-14,cy+8,16,22)); pygame.draw.ellipse(surf,(160,50,40),(cx+2,cy+10,14,18))
def draw_one_head(surf,cx,cy,alien,t,talking):
    kind,skin=alien["kind"],alien["skin"]
    open_amt=(0.35+0.65*abs(math.sin(t*14))) if talking else 0.08
    if alien.get("coat"): draw_coat(surf,cx,cy,alien["coat"])
    if alien.get("horns"): draw_horns(surf,cx,cy,tuple(max(0,c-40) for c in skin))
    if kind=="moth":
        flap=18*math.sin(t*8)
        pygame.draw.ellipse(surf,(200,180,80),(cx-70,cy-10+flap*0.2,50,70))
        pygame.draw.ellipse(surf,(200,180,80),(cx+20,cy-10-flap*0.2,50,70))
        pygame.draw.ellipse(surf,skin,(cx-28,cy-40,56,70))
    elif kind=="worm":
        pygame.draw.ellipse(surf,skin,(cx-30,cy-40,60,70))
        sway=8*math.sin(t*3)
        pygame.draw.ellipse(surf,skin,(cx-18+sway,cy+20,36,50))
        pygame.draw.ellipse(surf,skin,(cx-12-sway,cy+55,28,40))
    elif kind=="slug":
        pygame.draw.ellipse(surf,skin,(cx-40,cy-20,80,70))
        pygame.draw.ellipse(surf,tuple(max(0,c-30) for c in skin),(cx-22,cy+40,44,28))
    elif kind=="cephalopod":
        pygame.draw.ellipse(surf,skin,(cx-36,cy-36,72,64))
        for i in range(8):
            ang=0.4+i*0.28; wob=6*math.sin(t*3+i)
            pygame.draw.line(surf,skin,(cx,cy+20),(cx+math.cos(ang)*30+wob,cy+70+math.sin(t*2+i)*6),6)
    elif kind=="robot":
        head=alien.get("head","box")
        if head=="cylinder":
            pygame.draw.rect(surf,skin,(cx-28,cy-70,56,120),border_radius=4)
            pygame.draw.ellipse(surf,tuple(min(255,c+30) for c in skin),(cx-28,cy-82,56,24))
        elif head=="oval":
            pygame.draw.ellipse(surf,skin,(cx-56,cy-48,112,80))
        else:
            pygame.draw.rect(surf,skin,(cx-44,cy-56,88,104),border_radius=6)
        if alien.get("antenna"):
            sway=16*math.sin(t*2.2); pygame.draw.line(surf,(200,200,210),(cx,cy-56),(cx+sway,cy-92),3)
            pygame.draw.circle(surf,(80,255,200),(int(cx+sway),cy-94),5)
    elif kind=="mermaid":
        pygame.draw.ellipse(surf,(30,120,110),(cx-40,cy+30,80,70)); pygame.draw.ellipse(surf,skin,(cx-42,cy-58,84,100))
    elif kind=="avian":
        pygame.draw.ellipse(surf,skin,(cx-36,cy-50,72,80))
        pygame.draw.polygon(surf,(220,180,80),[(cx-40,cy),(cx-80,cy-10+8*math.sin(t*6)),(cx-36,cy+16)])
        pygame.draw.polygon(surf,(220,180,80),[(cx+40,cy),(cx+80,cy-10-8*math.sin(t*6)),(cx+36,cy+16)])
    elif kind=="crystal":
        pygame.draw.polygon(surf,skin,poly(cx,cy,6,52,t*0.2))
    elif kind=="conjoined":
        pygame.draw.ellipse(surf,skin,(cx-70,cy-40,70,90)); pygame.draw.ellipse(surf,skin,(cx,cy-40,70,90))
    elif kind=="triple":
        for ox in (-40,0,40): pygame.draw.circle(surf,skin,(cx+ox,cy-10),28)
    else:
        pygame.draw.ellipse(surf,skin,(cx-48,cy-64,96,120))
        if alien.get("organs"): draw_organs(surf,cx,cy)
    draw_eye_set(surf,cx,cy-6,alien,t)
    if alien.get("dog"):
        draw_dog_mouth(surf,cx,cy+6,talking)
    elif alien.get("beak"):
        pygame.draw.polygon(surf,(220,160,60),[(cx-8,cy+10),(cx+8,cy+10),(cx,cy+28)])
    elif kind=="robot":
        pygame.draw.rect(surf,(20,20,24),(cx-18,cy+16,36,int(6+16*open_amt)))
        if alien.get("fangs"): draw_fangs(surf,cx,cy+8)
    else:
        pygame.draw.ellipse(surf,(40,20,30),(cx-14,cy+20,28,int(8+16*open_amt)))
        if alien.get("fangs"): draw_fangs(surf,cx,cy+8)
    if alien.get("earrings"):
        pygame.draw.circle(surf,(240,200,80),(cx-40,cy-8),4); pygame.draw.circle(surf,(240,200,80),(cx+40,cy-8),4)
def draw_monitor_bg(surf,rect,alien,t):
    pygame.draw.rect(surf,(10,16,26),rect); pygame.draw.rect(surf,(70,110,130),rect,2)
    style=alien.get("bg","techno"); inner=rect.inflate(-8,-8)
    if style=="aquatic":
        pygame.draw.rect(surf,(6,28,48),inner)
        for i in range(16):
            bx=rect.x+10+(i*29+int(t*30))%(rect.w-20)
            by=rect.bottom-10-((i*47+int(t*55))%(rect.h-20))
            pygame.draw.circle(surf,(90,190,210),(bx,by),2+i%5,1)
    elif style=="floral":
        pygame.draw.rect(surf,(18,42,20),inner)
        for i in range(12):
            fx=rect.x+16+(i*31)%(rect.w-28); fy=rect.y+20+(i*23+int(8*math.sin(t+i)))%(rect.h-36)
            pygame.draw.circle(surf,(170,50,80),(fx,fy),7)
    elif style=="bridge":
        pygame.draw.rect(surf,(16,20,34),inner)
        pygame.draw.rect(surf,(50,60,80),(rect.x+8,rect.centery+10,rect.w-16,10))
        for i in range(4):
            pygame.draw.circle(surf,ALIENS[(hash(alien["name"])+i*17)%len(ALIENS)]["skin"],(rect.x+36+i*44,rect.centery-8),11)
    else:
        pygame.draw.rect(surf,(8,14,24),inner)
        for i in range(8):
            y=rect.y+16+i*16
            pygame.draw.line(surf,(30,90,80),(rect.x+10,y+int(5*math.sin(t*5+i))),(rect.right-10,y),1)
    bar=pygame.Rect(rect.x+6,rect.bottom-46,rect.w-12,40)
    pygame.draw.rect(surf,(22,28,38),bar,border_radius=4)
    for i in range(5):
        lx=bar.x+10+i*28
        pygame.draw.rect(surf,(40,50,60),(lx,bar.y+8,10,26))
        throw=4 if math.sin(t*1.3+i)>0 else 16
        pygame.draw.rect(surf,(200,80,60) if i%2 else (80,180,120),(lx+1,bar.y+throw,8,10))
    for i in range(4):
        on=(int(t*3)+i)%3!=0
        pygame.draw.circle(surf,(80,255,140) if on else (40,50,40),(bar.right-12-i*14,bar.y+20),4)
def draw_alien_face(surf,cx,cy,alien,t,talking):
    hx,hy=head_offset(alien,t); face=pygame.Surface((240,280),pygame.SRCALPHA)
    draw_one_head(face,120,120,alien,t,talking)
    face.set_alpha(140 if alien.get("trans_head") else alien.get("alpha",255))
    surf.blit(face,(cx-120+hx,cy-120+hy))
def make_element_contract(ai):
    if random.random()<0.12:
        allowed=random.sample(ALL_SYMBOLS,10); examples=random.sample(allowed,5)
        name,blurb="Ten named species","A private list of ten elements."
    else:
        grp=random.choice(ELEMENT_GROUPS); allowed=list(grp["symbols"])
        examples=random.sample(allowed,min(5,len(allowed))); name,blurb=grp["name"],grp["blurb"]
    return {"alien":ai,"kind":"element","loot_id":None,"group_name":name,"blurb":blurb,"allowed":allowed,"examples":examples,"need":random.randint(3,10),"got":0,"pay":random.randint(40,100)*1000}
def roll_offer(has_gun):
    ai=random.randrange(len(ALIENS)); alien=ALIENS[ai]; use_loot=has_gun and random.random()<0.5
    if not use_loot:
        if has_gun and alien["want"]=="gem":
            spec=random.choice(GEMS); return {"alien":ai,"kind":"gem","loot_id":spec["id"],"need":random.randint(3,10),"got":0,"pay":random.randint(40,100)*1000}
        if has_gun and alien["want"]=="gear":
            spec=random.choice(GEAR); return {"alien":ai,"kind":"gear","loot_id":spec["id"],"need":random.randint(3,10),"got":0,"pay":random.randint(40,100)*1000}
        return make_element_contract(ai)
    if alien["want"]=="gear": spec,kind=random.choice(GEAR),"gear"
    elif alien["want"]=="gem": spec,kind=random.choice(GEMS),"gem"
    else:
        kind=random.choice(["gem","gear"]); spec=random.choice(GEMS if kind=="gem" else GEAR)
    return {"alien":ai,"kind":kind,"loot_id":spec["id"],"need":random.randint(3,10),"got":0,"pay":random.randint(40,100)*1000}
def drop_loot(drops,x,y,rich=False,jackpot=False):
    n=random.randint(50,70) if jackpot else (random.randint(14,22) if rich else random.randint(5,7))
    for _ in range(n): drops.append(Loot(x+random.uniform(-22,22),y+random.uniform(-22,22),random.choice(GEMS+GEAR)))
def note_loot(ship,spec):
    if spec.get("shape"): ship.found_gems.add(spec["id"])
    elif spec.get("cells"):
        ship.found_gear.add(spec["id"])
        if ship.found_gear>=set(GEAR_IDS): ship.warp=True
def collect_loot_item(ship,loot,mission,loot_market):
    spec=loot.spec; loot.alive=False; note_loot(ship,spec)
    if mission and mission.get("loot_id")==spec["id"] and mission["got"]<mission["need"]:
        mission["got"]+=1
        if mission["got"]>=mission["need"]:
            ship.score+=mission["pay"]; return f"Contract complete. +{mission['pay']:,} c",None
        return f"Contract {mission['got']}/{mission['need']} {spec['name']}",mission
    val=loot_spot_price(spec,loot_market,ship.price_bonus); ship.score+=val
    extra="  WARP unlocked (G)" if ship.warp and spec.get("cells") and ship.found_gear>=set(GEAR_IDS) else ""
    return f"+{val} c  {spec['name']}{extra}",mission
def apply_damage(ship,lives):
    if ship.immortal: return False,""
    if ship.shield and ship.shield_hits>0:
        use=min(lives,ship.shield_hits); ship.shield_hits-=use; lives-=use
        if ship.shield_hits<=0: ship.shield=False
        if lives<=0: return False,"Shield ate the hit."
    if ship.invuln>0: return False,""
    ship.lives-=lives; ship.invuln=2.0
    return ship.lives<=0,"Pirate fire!"
def offer_name(offer):
    if offer.get("kind")=="element": return offer.get("group_name","Elements")
    if offer.get("loot_id"): return LOOT_BY_ID[offer["loot_id"]]["name"]
    return "Tour"
def wrap_text(text,width=52):
    words,lines,cur=text.split(),[],""
    for w in words:
        trial=(cur+" "+w).strip()
        if len(trial)<=width: cur=trial
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    return lines
def fire_gun(ship,bullets):
    spec=GUNS.get(ship.gun)
    if not spec: return
    for k in range(spec["n"]):
        ang=ship.ang+(k-(spec["n"]-1)/2)*spec["spread"]
        bullets.append(Bullet(ship.x+math.cos(ang)*18,ship.y+math.sin(ang)*18,ship.vx+math.cos(ang)*spec["spd"],ship.vy+math.sin(ang)*spec["spd"],dmg=spec["dmg"],life=spec["life"],color=spec["color"],r=6 if ship.gun=="torpedo" else 4))
        if ship.companion:
            bullets.append(Bullet(ship.cx+math.cos(ang)*14,ship.cy+math.sin(ang)*14,ship.vx+math.cos(ang)*spec["spd"],ship.vy+math.sin(ang)*spec["spd"],dmg=spec["dmg"],life=spec["life"],color=spec["color"]))
    ship.fire_cd=spec["rate"]
def draw_dialog(screen,font,small,offer,t,tour=False,remain=0,mouth_on=True):
    overlay=pygame.Surface((WIDTH,HEIGHT),pygame.SRCALPHA); overlay.fill((4,8,16,200)); screen.blit(overlay,(0,0))
    box=pygame.Rect(50,40,WIDTH-100,HEIGHT-80)
    pygame.draw.rect(screen,(18,26,40),box,border_radius=10); pygame.draw.rect(screen,(140,200,160),box,2,border_radius=10)
    alien=ALIENS[offer["alien"]]; mon=pygame.Rect(box.x+16,box.y+64,250,300)
    draw_monitor_bg(screen,mon,alien,t); draw_alien_face(screen,mon.centerx,mon.centery-10,alien,t,mouth_on)
    draw_wanted_preview(screen,font,small,offer,box.right-130,box.y+190)
    screen.blit(font.render(alien["name"],True,(230,240,255)),(box.x+280,box.y+18))
    screen.blit(small.render(f"{alien['title']}   [{alien['kind']}/{alien['voice']}]",True,(160,190,170)),(box.x+280,box.y+50))
    y=box.y+84
    if tour:
        screen.blit(small.render(f"CATALOG  {offer['alien']+1}/{len(ALIENS)}   {remain:.1f}s",True,(230,230,210)),(box.x+280,y)); y+=24
        screen.blit(small.render("Esc or N ends the tour.",True,(200,210,180)),(box.x+280,y)); return
    screen.blit(small.render(f"Seek {offer['need']} units of:  {offer_name(offer)}",True,(230,230,210)),(box.x+280,y)); y+=22
    if offer.get("kind")=="element":
        for line in wrap_text(offer.get("blurb",""),54):
            screen.blit(small.render(line,True,(190,205,200)),(box.x+280,y)); y+=18
        screen.blit(small.render("Examples: "+", ".join(offer.get("examples",[])),True,(180,200,160)),(box.x+280,y)); y+=20
    screen.blit(small.render(f"Wire on quota: {offer.get('pay',0):,} c",True,(210,215,220)),(box.x+280,y)); y+=24
    screen.blit(small.render("Y / Enter accept     N / Esc decline",True,(200,210,180)),(box.x+280,y))
def draw_still_need(surf,tiny,ship,x,y):
    surf.blit(tiny.render("STILL NEED",True,(140,190,210)),(x,y)); y+=16
    miss_g=[g for g in GEMS if g["id"] not in ship.found_gems]
    miss_p=[g for g in GEAR if g["id"] not in ship.found_gear]
    miss_e=[s for s in ALL_SYMBOLS if s not in ship.found_elems]
    surf.blit(tiny.render(f"Jewels {len(miss_g)}/{len(GEMS)}",True,(200,200,210)),(x,y)); y+=14
    for i,g in enumerate(miss_g[:8]):
        draw_gem_shape(surf,x+10+(i%8)*16,y+8,g,0.45)
    y+=20
    surf.blit(tiny.render(f"Parts {len(miss_p)}/{len(GEAR)}",True,(200,200,210)),(x,y)); y+=14
    for i,g in enumerate(miss_p[:8]):
        draw_gear_shape(surf,x+12+(i%8)*18,y+8,g,0.35)
    y+=22
    surf.blit(tiny.render(f"Elems {len(miss_e)}/{len(ALL_SYMBOLS)}",True,(200,200,210)),(x,y)); y+=14
    for i,s in enumerate(miss_e[:36]):
        surf.blit(tiny.render(s,True,ELEMENT_INFO[s]["color"]),(x+(i%9)*30,y+(i//9)*12))
    return y+50
def draw_panel(surf,font,small,tiny,quotes,ship,msg,mission,t,scare_t=0):
    glass=pygame.Surface((PANEL_W,HEIGHT),pygame.SRCALPHA); glass.fill((8,12,22,200)); surf.blit(glass,(VIEW_W,0))
    pygame.draw.line(surf,(70,120,160),(VIEW_W,0),(VIEW_W,HEIGHT),2)
    x,y=VIEW_W+16,8
    surf.blit(font.render("SPACE MINER",True,(220,235,255)),(x,y)); y+=28
    surf.blit(small.render("LOCAL MARKET  (top 5)",True,(140,190,210)),(x,y)); y+=16
    flash=int(t*3)%2==0
    if not quotes:
        surf.blit(tiny.render("No quotes in range",True,(140,150,160)),(x,y)); y+=16
    for q in quotes[:5]:
        pygame.draw.circle(surf,q["color"],(x+8,y+7),5)
        col=(255,230,90) if q.get("peak") and flash else (220,220,230)
        surf.blit(tiny.render(q["label"],True,col),(x+20,y))
        surf.blit(tiny.render(f"{q['price']}c",True,col),(x+200,y)); y+=13
        track=pygame.Rect(x+20,y+1,240,6)
        pygame.draw.rect(surf,(30,40,50),track,border_radius=3)
        mul=q.get("mul",1.0)
        fill_w=int(240*clamp((mul-0.55)/(1.85-0.55),0.0,1.0))
        if fill_w>0:
            pygame.draw.rect(surf,q["color"],(track.x,track.y,fill_w,track.h),border_radius=3)
        if q.get("peak"):
            pygame.draw.rect(surf,(255,230,90) if flash else q["color"],track,1,border_radius=3)
        y+=10
    y+=4
    surf.blit(small.render(f"Bucks: {ship.score:,}",True,(255,220,120)),(x,y)); y+=16
    surf.blit(small.render(f"Lives: {ship.lives}/{MAX_LIVES}",True,(255,140,140)),(x,y)); y+=16
    flags=[]
    if ship.immortal: flags.append("IMM")
    if ship.warp: flags.append("WARP")
    if ship.can_resurrect: flags.append("RISE")
    if ship.cloak: flags.append("VEIL")
    if scare_t>0: flags.append(f"SCARE {scare_t:.0f}")
    if flags: surf.blit(tiny.render(" ".join(flags),True,(180,255,200)),(x,y)); y+=14
    if mission: surf.blit(tiny.render(f"{mission['got']}/{mission['need']} {offer_name(mission)[:16]}",True,(200,230,160)),(x,y)); y+=14
    y=draw_still_need(surf,tiny,ship,x,y+2)
    if msg: surf.blit(tiny.render(msg,True,(255,230,160)),(x,HEIGHT-28))
def draw_store(screen,font,small,ship,sel,tractor_sel,notice):
    overlay=pygame.Surface((WIDTH,HEIGHT),pygame.SRCALPHA); overlay.fill((4,8,16,210)); screen.blit(overlay,(0,0))
    box=pygame.Rect(50,24,WIDTH-100,HEIGHT-48)
    pygame.draw.rect(screen,(16,24,38),box,border_radius=10); pygame.draw.rect(screen,(90,160,200),box,2,border_radius=10)
    screen.blit(font.render("ORBITAL CHANDLERY",True,(230,240,255)),(box.x+24,box.y+12))
    screen.blit(small.render(f"Account: {ship.score:,} c",True,(255,220,120)),(box.x+24,box.y+46))
    item=STORE_ITEMS[sel]
    screen.blit(small.render(f"Selected: {item['name']}  x {owned_count(ship,item['id'])}",True,(180,220,200)),(box.x+320,box.y+46))
    y,start=box.y+78,max(0,sel-7) if sel>=8 else 0
    for i,it in enumerate(STORE_ITEMS[start:start+8],start=start):
        row=pygame.Rect(box.x+24,y,620,46)
        pygame.draw.rect(screen,(40,70,50) if i==sel else (24,32,48),row,border_radius=6)
        screen.blit(small.render(f"{it['name']}   {it['cost']:,} c   (have {owned_count(ship,it['id'])})",True,(240,240,230)),(row.x+12,row.y+5))
        screen.blit(small.render(it["desc"],True,(160,180,200)),(row.x+12,row.y+24)); y+=50
    side=pygame.Rect(box.right-430,box.y+78,400,box.h-140)
    pygame.draw.rect(screen,(20,28,42),side,border_radius=6)
    t0=clamp(tractor_sel-5,0,max(0,len(ALL_SYMBOLS)-11)); ey=side.y+12
    for j in range(t0,min(t0+11,len(ALL_SYMBOLS))):
        info=ELEMENT_INFO[ALL_SYMBOLS[j]]; mark=">" if j==tractor_sel else " "; own="*" if ALL_SYMBOLS[j] in ship.tractors else " "
        screen.blit(small.render(f"{mark}{own}{info['z']:3d} {info['name']}",True,(255,255,210) if j==tractor_sel else info["color"]),(side.x+10,ey)); ey+=20
    if notice: screen.blit(small.render(notice,True,(255,220,140)),(box.x+24,box.bottom-28))
def draw_help(screen,font,small,page):
    overlay=pygame.Surface((WIDTH,HEIGHT),pygame.SRCALPHA); overlay.fill((4,8,16,220)); screen.blit(overlay,(0,0))
    box=pygame.Rect(60,36,WIDTH-120,HEIGHT-72)
    pygame.draw.rect(screen,(14,20,34),box,border_radius=10); pygame.draw.rect(screen,(90,160,200),box,2,border_radius=10)
    screen.blit(font.render(f"BRIEFING  {page+1}/{len(HELP_PAGES)}",True,(230,240,255)),(box.x+20,box.y+12))
    y=box.y+48
    for line in HELP_PAGES[page]:
        screen.blit(small.render(line[:88],True,(210,235,255) if line in HELP_TITLES else (190,200,210)),(box.x+20,y)); y+=18
def draw_cheat(screen,font,small,text):
    overlay=pygame.Surface((WIDTH,HEIGHT),pygame.SRCALPHA); overlay.fill((4,8,16,180)); screen.blit(overlay,(0,0))
    box=pygame.Rect(200,HEIGHT//2-60,WIDTH-400,120)
    pygame.draw.rect(screen,(16,24,38),box,border_radius=8); pygame.draw.rect(screen,(200,220,120),box,2,border_radius=8)
    screen.blit(font.render("CHEAT CONSOLE",True,(230,240,180)),(box.x+16,box.y+12))
    screen.blit(small.render(text+"_",True,(255,255,210)),(box.x+16,box.y+56))
    screen.blit(small.render("Enter run   Esc cancel",True,(160,170,150)),(box.x+16,box.y+86))

def main(load_on_start=False):
    pygame.mixer.pre_init(SAMPLE_RATE,size=-16,channels=2,buffer=512)
    pygame.init(); pygame.mixer.init(SAMPLE_RATE,size=-16,channels=2)
    screen=pygame.display.set_mode((WIDTH,HEIGHT)); pygame.display.set_caption("Space Miner")
    clock=pygame.time.Clock()
    font,small,tiny,big=[pygame.font.SysFont("consolas",s) for s in (24,15,13,48)]
    rocket_snd,warn_snd=make_noise_rumble(),make_warning()
    buy_snd,shot_snd=make_blip(880,90),make_blip(420,50,0.10)
    voices=[make_alien_voice(a) for a in ALIENS]
    rocket_chan,warn_chan,talk_chan=pygame.mixer.Channel(0),pygame.mixer.Channel(1),pygame.mixer.Channel(2)
    ship,planets=Ship(),{}
    market={sym:1.0 for sym,_ in ELEMENTS}; market_vel={sym:0.0 for sym,_ in ELEMENTS}
    loot_market={spec["id"]:1.0 for spec in GEMS+GEAR}; loot_vel={spec["id"]:0.0 for spec in GEMS+GEAR}
    t=game_time=0.0; w1=w2=game_over=False
    msg,msg_t,warn_cool,regen_t,space_timer="",0.0,0.0,0.0,0.0
    bullets,pirates,drops=[],[],[]
    store_open=help_open=warp_mode=cheat_open=False
    help_page=store_sel=tractor_sel=0
    store_notice,mission,offer="",None,None
    cheat_text=""; show_tour=False; show_i,show_t,voice_wait=0,0.0,0.0
    cam_off_x=cam_off_y=0.0; rise_t=RESURRECT_WINDOW
    mouth_t,mouth_on=0.0,True
    scare_t,pirate_kills,scare_need=0.0,0,random.randint(2,3)
    if load_on_start and os.path.exists(SAVE_PATH):
        try: game_time,w1,w2,mission=load_game(SAVE_PATH,ship,market,loot_market); msg,msg_t="Save loaded.",2.0
        except Exception: msg,msg_t="Save unreadable.",2.0
    running=True
    def apply_cheat(cmd):
        nonlocal msg,msg_t,show_tour,show_i,show_t,offer,pirates,drops
        cmd=cmd.strip().lower()
        if not cmd.startswith("#"): cmd="#"+cmd
        if cmd=="#immortal": ship.immortal=True; msg,msg_t="Immortal.",2.0
        elif cmd=="#mortal": ship.immortal=False; msg,msg_t="Mortal again.",2.0
        elif cmd=="#give": grant_chandlery(ship); msg,msg_t="Chandlery dumped. +10000c",2.5
        elif cmd=="#show":
            show_tour,show_i,show_t=True,0,SHOW_DWELL; offer={"alien":0,"kind":"tour","need":0,"pay":0}; talk_chan.play(voices[0])
        elif cmd=="#k":
            for pr in list(pirates): drop_loot(drops,pr.x,pr.y,rich=True,jackpot=pr.was_shielded)
            pirates.clear(); msg,msg_t="Pirates hulled.",2.0
        elif cmd=="#warp": ship.warp=True; msg,msg_t="Warp granted. Press G.",2.0
        elif cmd=="#elements": grant_catalog(ship); msg,msg_t="Full catalog. Rise unlocked.",2.5
        else: msg,msg_t=f"Unknown code {cmd}",2.0
    while running:
        dt=min(clock.tick(FPS)/1000.0,0.05); t+=dt
        paused=store_open or help_open or game_over or offer is not None or warp_mode or show_tour or cheat_open
        if not paused:
            game_time+=dt
            if scare_t>0: scare_t=max(0.0,scare_t-dt)
        warn_cool=max(0.0,warn_cool-dt); ship.fire_cd=max(0.0,ship.fire_cd-dt)
        if offer is not None:
            mouth_t+=dt
            if mouth_on and mouth_t>=random.uniform(3,10): mouth_on,mouth_t=False,0.0
            elif (not mouth_on) and mouth_t>=random.uniform(0.5,2.0): mouth_on,mouth_t=True,0.0
        if show_tour:
            show_t-=dt; voice_wait-=dt
            if show_t<=0:
                show_i=(show_i+1)%len(ALIENS); show_t=SHOW_DWELL
                offer={"alien":show_i,"kind":"tour","need":0,"pay":0}; talk_chan.play(voices[show_i])
                voice_wait=random.uniform(5,10) if ALIENS[show_i]["voice"] in ("dtmf","teletype") else 99
            elif ALIENS[offer["alien"]]["voice"] in ("dtmf","teletype") and voice_wait<=0:
                talk_chan.play(voices[offer["alien"]]); voice_wait=random.uniform(5,10)
        if game_over and ship.can_resurrect: rise_t-=dt
        for e in pygame.event.get():
            if e.type==pygame.QUIT: running=False
            elif e.type==pygame.KEYDOWN:
                if cheat_open:
                    if e.key==pygame.K_RETURN: apply_cheat(cheat_text); cheat_open,cheat_text=False,""
                    elif e.key==pygame.K_ESCAPE: cheat_open,cheat_text=False,""
                    elif e.key==pygame.K_BACKSPACE: cheat_text=cheat_text[:-1]
                    elif e.unicode and e.unicode.isprintable(): cheat_text+=e.unicode
                    continue
                if e.key in (pygame.K_BACKQUOTE,) or e.unicode=="~":
                    cheat_open,cheat_text=True,""; continue
                if show_tour and e.key in (pygame.K_n,pygame.K_ESCAPE):
                    show_tour,offer=False,None; talk_chan.stop(); continue
                if offer is not None and not show_tour:
                    if e.key in (pygame.K_y,pygame.K_RETURN):
                        mission,offer=dict(offer),None; talk_chan.stop(); msg,msg_t="Contract accepted.",2.0
                    elif e.key in (pygame.K_n,pygame.K_ESCAPE):
                        offer=None; talk_chan.stop(); msg,msg_t="Contract declined.",1.6
                    continue
                if warp_mode:
                    if e.key in (pygame.K_RETURN,pygame.K_g,pygame.K_ESCAPE): warp_mode=False
                    continue
                if e.key==pygame.K_ESCAPE:
                    if store_open or help_open: store_open=help_open=False
                    else: running=False
                elif e.key==pygame.K_g and ship.warp and not game_over:
                    warp_mode=True; cam_off_x=cam_off_y=0.0
                elif e.key in (pygame.K_h,pygame.K_F1) and not game_over:
                    help_open=not help_open
                    if help_open: store_open,help_page=False,0
                elif help_open and e.key in (pygame.K_DOWN,pygame.K_s,pygame.K_PAGEDOWN): help_page=min(len(HELP_PAGES)-1,help_page+1)
                elif help_open and e.key in (pygame.K_UP,pygame.K_w,pygame.K_PAGEUP): help_page=max(0,help_page-1)
                elif e.key in (pygame.K_b,pygame.K_TAB) and not game_over:
                    store_open=not store_open
                    if store_open: help_open=False
                elif e.key==pygame.K_F5:
                    save_game(SAVE_PATH,ship,market,loot_market,game_time,w1,w2,mission); msg,msg_t="Game saved.",2.0
                elif e.key==pygame.K_F9 and os.path.exists(SAVE_PATH):
                    pygame.quit(); return main(True)
                elif game_over and e.key==pygame.K_y and ship.can_resurrect and rise_t>0:
                    game_over=False; ship.lives=max(3,ship.lives); ship.invuln=3.0
                    ship.x+=random.uniform(-200,200); rise_t=RESURRECT_WINDOW; msg,msg_t="Resurrected.",2.0
                elif game_over and e.key==pygame.K_r:
                    pygame.quit(); return main()
                elif store_open:
                    if e.key in (pygame.K_UP,pygame.K_w): store_sel=(store_sel-1)%len(STORE_ITEMS)
                    elif e.key in (pygame.K_DOWN,pygame.K_s): store_sel=(store_sel+1)%len(STORE_ITEMS)
                    elif e.key in (pygame.K_LEFTBRACKET,pygame.K_LEFT): tractor_sel=(tractor_sel-1)%len(ALL_SYMBOLS)
                    elif e.key in (pygame.K_RIGHTBRACKET,pygame.K_RIGHT): tractor_sel=(tractor_sel+1)%len(ALL_SYMBOLS)
                    elif e.key==pygame.K_RETURN:
                        item=STORE_ITEMS[store_sel]
                        if item["id"]=="tractor" and ALL_SYMBOLS[tractor_sel] in ship.tractors: store_notice="Already own that beam."
                        elif item["id"]=="companion" and ship.companion: store_notice="Companion already docked."
                        elif ship.score<item["cost"]: store_notice="Not enough credits."
                        elif item["id"]=="tractor":
                            ship.tractors.add(ALL_SYMBOLS[tractor_sel]); ship.score-=item["cost"]
                            ship.purchases[item["id"]]=ship.purchases.get(item["id"],0)+1; buy_snd.play()
                            store_notice=f"Beam for {ALL_SYMBOLS[tractor_sel]}."
                        else:
                            ok=apply_store_item(ship,item["id"])
                            if ok is False: store_notice="Cannot buy that."
                            else:
                                ship.score-=item["cost"]; ship.purchases[item["id"]]=ship.purchases.get(item["id"],0)+1
                                buy_snd.play(); store_notice=f"Purchased {item['name']}."
        keys,mouse=pygame.key.get_pressed(),pygame.mouse.get_pressed()
        if warp_mode:
            spd=520
            if keys[pygame.K_LEFT] or keys[pygame.K_a]: cam_off_x-=spd*dt
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]: cam_off_x+=spd*dt
            if keys[pygame.K_UP] or keys[pygame.K_w]: cam_off_y-=spd*dt
            if keys[pygame.K_DOWN] or keys[pygame.K_s]: cam_off_y+=spd*dt
        ccx=int(math.floor((ship.x+(cam_off_x if warp_mode else 0))/CHUNK))
        ccy=int(math.floor((ship.y+(cam_off_y if warp_mode else 0))/CHUNK))
        for ix in range(ccx-GEN_RADIUS,ccx+GEN_RADIUS+1):
            for iy in range(ccy-GEN_RADIUS,ccy+GEN_RADIUS+1): generate_chunk(ix,iy,planets)
        nearby=[p for p in planets.values() if abs(p.x-ship.x)<CHUNK*1.6 and abs(p.y-ship.y)<CHUNK*1.6]
        nearest=min(nearby,key=lambda p:(p.x-ship.x)**2+(p.y-ship.y)**2) if nearby else None
        in_system,system_elems=False,[]
        if nearest and math.hypot(nearest.x-ship.x,nearest.y-ship.y)-nearest.r<SYSTEM_RANGE:
            in_system,system_elems=True,nearest.elements
        if offer is not None and not talk_chan.get_busy() and not show_tour:
            talk_chan.play(voices[offer["alien"]])
            if ALIENS[offer["alien"]]["voice"] in ("dtmf","teletype"): voice_wait=random.uniform(5,10)
        if offer is not None and not show_tour and ALIENS[offer["alien"]]["voice"] in ("dtmf","teletype"):
            voice_wait-=dt
            if voice_wait<=0: talk_chan.play(voices[offer["alien"]]); voice_wait=random.uniform(5,10)
        if ship.companion:
            ship.tether_ang=lerp_angle(ship.tether_ang,ship.ang+math.pi/2,TETHER_SWING*dt)
            ship.cx,ship.cy=companion_pos(ship)
        else: ship.cx,ship.cy=ship.x,ship.y
        if not paused:
            if in_system:
                space_timer=0.0
                for p in pirates: p.flee=True
            else:
                space_timer+=dt
                if mission is None and offer is None and space_timer>=ENCOUNTER_WAIT:
                    space_timer=0.0; offer=roll_offer(ship.gun is not None); mouth_on,mouth_t=True,0.0
                elif mission is not None and scare_t<=0 and space_timer>=PIRATE_WAIT and len(pirates)<3:
                    space_timer=0.0; ang=random.random()*math.tau
                    px,py=ship.x+math.cos(ang)*520,ship.y+math.sin(ang)*520
                    if ship.gun and random.random()<0.12:
                        a=Pirate(px,py,deadly=True,shielded=random.random()<0.35)
                        b=Pirate(px+40,py+30,partner=a,deadly=True,shielded=random.random()<0.35)
                        a.partner=b; pirates.extend([a,b])
                    else: pirates.append(Pirate(px,py,shielded=random.random()<0.22))
            thrust=THRUST*(1.0+0.22*ship.engine_boost)
            if keys[pygame.K_LEFT] or keys[pygame.K_a]: ship.ang-=TURN*dt
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]: ship.ang+=TURN*dt
            ship.thrusting=False
            if keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_SPACE]:
                ship.vx+=math.cos(ship.ang)*thrust*dt; ship.vy+=math.sin(ship.ang)*thrust*dt; ship.thrusting=True
            if keys[pygame.K_DOWN] or keys[pygame.K_s]:
                ship.vx-=math.cos(ship.ang)*thrust*0.45*dt; ship.vy-=math.sin(ship.ang)*thrust*0.45*dt
            if ship.gun and (keys[pygame.K_f] or keys[pygame.K_LCTRL] or mouse[0]) and ship.fire_cd<=0:
                fire_gun(ship,bullets); shot_snd.play()
            if ship.regen and ship.lives<MAX_LIVES:
                regen_t+=dt
                if regen_t>=90: regen_t=0; ship.lives+=1
        if ship.thrusting and not paused:
            if not rocket_chan.get_busy(): rocket_chan.play(rocket_snd,loops=-1)
        else: rocket_chan.fadeout(80)
        if not paused:
            tick_market(market,market_vel,dt); tick_market(loot_market,loot_vel,dt)
            w1,w2=reinforce_mines(planets,game_time,w1,w2)
            ax,ay=gravity_from_planets(ship.x,ship.y,nearby)
            ship.vx+=ax*dt; ship.vy+=ay*dt
            spd=math.hypot(ship.vx,ship.vy)
            if spd>MAX_SPEED: ship.vx*=MAX_SPEED/spd; ship.vy*=MAX_SPEED/spd
            ship.vx*=DRAG; ship.vy*=DRAG; ship.x+=ship.vx*dt; ship.y+=ship.vy*dt
            if ship.invuln>0: ship.invuln-=dt
            if ship.companion:
                ship.tether_ang=lerp_angle(ship.tether_ang,ship.ang+math.pi/2,TETHER_SWING*dt)
                ship.cx,ship.cy=companion_pos(ship)
            pickup_r=(1.6 if ship.magnet else 1.0)*ship.cargo_bonus
            seek_r=MINE_SEEK_R*(0.45 if ship.quiet else 1.0); mine_seeking=False
            for p in nearby:
                for a in p.asteroids:
                    if a.mine and not a.alive:
                        a.respawn_in-=dt
                        if a.respawn_in<=0: park_on_orbit(a)
                        continue
                    if not a.alive: continue
                    if ship.tractors and (not a.mine) and a.symbol in ship.tractors:
                        dx,dy=ship.x-a.x,ship.y-a.y; d=math.hypot(dx,dy)
                        if 1<d<TRACTOR_RANGE: a.vx+=dx/d*TRACTOR_ACC*dt; a.vy+=dy/d*TRACTOR_ACC*dt
                    if a.mine:
                        d=math.hypot(ship.x-a.x,ship.y-a.y); a.chasing=d<seek_r and d>1
                        if a.chasing:
                            mine_seeking=True; a.vx+=(ship.x-a.x)/max(d,1)*MINE_SEEK_ACC*dt; a.vy+=(ship.y-a.y)/max(d,1)*MINE_SEEK_ACC*dt
                        else:
                            gx,gy=gravity_from_planets(a.x,a.y,nearby); a.vx+=gx*dt; a.vy+=gy*dt; keep_in_orbit(a,dt)
                    else:
                        gx,gy=gravity_from_planets(a.x,a.y,nearby); a.vx+=gx*dt; a.vy+=gy*dt; keep_in_orbit(a,dt)
                    if not a.chasing: a.vx*=0.996; a.vy*=0.996
                    cap=MINE_MAX_SPEED if a.mine else ASTEROID_MAX_SPEED
                    asp=math.hypot(a.vx,a.vy)
                    if asp>cap: a.vx*=cap/asp; a.vy*=cap/asp
                    a.x+=a.vx*dt; a.y+=a.vy*dt; crashed=False
                    for world in nearby:
                        dx,dy=a.x-world.x,a.y-world.y; d=math.hypot(dx,dy)
                        if 0<d<world.r+a.r:
                            if a.mine and a.chasing: arm_respawn(a); crashed=True; break
                            nx,ny=dx/d,dy/d; a.x,a.y=world.x+nx*(world.r+a.r),world.y+ny*(world.r+a.r)
                    if crashed or not a.alive: continue
                    hit_ship=math.hypot(a.x-ship.x,a.y-ship.y)<a.r+ship.r*pickup_r
                    hit_comp=ship.companion and math.hypot(a.x-ship.cx,a.y-ship.cy)<a.r+12*pickup_r
                    hit_line=ship.companion and dist_point_seg(a.x,a.y,ship.x,ship.y,ship.cx,ship.cy)<10
                    if hit_ship or hit_comp or hit_line:
                        if a.mine:
                            if ship.immortal: arm_respawn(a)
                            elif ship.shield and ship.shield_hits>0:
                                ship.shield_hits-=1
                                if ship.shield_hits<=0: ship.shield=False
                                arm_respawn(a)
                            elif ship.invuln<=0:
                                ship.lives-=1; ship.invuln=2.0
                                if ship.lives<=0: game_over,rise_t=True,RESURRECT_WINDOW
                                arm_respawn(a)
                            else: arm_respawn(a)
                        elif mission and mission.get("kind")=="element" and a.symbol in mission.get("allowed",[]) and mission["got"]<mission["need"]:
                            mission["got"]+=1; ship.found_elems.add(a.symbol); a.alive=False
                            if mission["got"]>=mission["need"]:
                                ship.score+=mission["pay"]; msg,msg_t=f"Contract complete. +{mission['pay']:,} c",2.4; mission=None
                            else: msg,msg_t=f"Contract {mission['got']}/{mission['need']} {a.symbol}",1.2
                        else:
                            info=ELEMENT_INFO[a.symbol]
                            price=clamp(int(info["base"]*market[a.symbol]*ship.price_bonus),100,1500)
                            ship.score+=price; ship.value_toward_life+=price; ship.found_elems.add(a.symbol)
                            need=value_needed(ship.lives); gained=False
                            while need and ship.value_toward_life>=need and ship.lives<MAX_LIVES:
                                ship.value_toward_life-=need; ship.lives+=1; need=value_needed(ship.lives); gained=True
                            msg,msg_t=((f"Bonus life! ({ship.lives}/{MAX_LIVES})",2.0) if gained else (f"+{price} c  {info['name']}",1.4))
                            a.alive=False
            for loot in drops:
                if not loot.alive: continue
                loot.x+=loot.vx*dt; loot.y+=loot.vy*dt; loot.vx*=0.99; loot.vy*=0.99
                touch=math.hypot(loot.x-ship.x,loot.y-ship.y)<16*pickup_r
                if ship.companion:
                    touch=touch or math.hypot(loot.x-ship.cx,loot.y-ship.cy)<16*pickup_r
                    touch=touch or dist_point_seg(loot.x,loot.y,ship.x,ship.y,ship.cx,ship.cy)<10
                if touch:
                    text,mission=collect_loot_item(ship,loot,mission,loot_market); msg,msg_t=text,1.6
            live_p=[]
            for pr in pirates:
                scared=scare_t>0 or pr.flee or in_system
                if not scared:
                    pr.lock_t-=dt
                    if pr.lock_t<=0:
                        jitter=140 if ship.cloak else 18
                        pr.gx=ship.x+random.uniform(-jitter,jitter)
                        pr.gy=ship.y+random.uniform(-jitter,jitter)
                        pr.lock_t=random.uniform(0.35,1.1) if ship.cloak else random.uniform(0.15,0.4)
                    dx,dy=pr.gx-pr.x,pr.gy-pr.y
                else:
                    dx,dy=pr.x-ship.x,pr.y-ship.y
                d=math.hypot(dx,dy) or 1
                pr.vx+=dx/d*PIRATE_ACC*dt; pr.vy+=dy/d*PIRATE_ACC*dt
                if not scared:
                    pr.cd-=dt
                    if pr.cd<=0:
                        pr.cd=PIRATE_SHOT_RATE
                        miss_p=0.82 if ship.cloak else 0.5
                        if random.random()>=miss_p:
                            j=220 if ship.cloak else 90
                            jx,jy=random.uniform(-j,j),random.uniform(-j,j)
                            bullets.append(Bullet(pr.x,pr.y,(pr.gx+jx-pr.x)/d*PIRATE_SHOT_SPEED,(pr.gy+jy-pr.y)/d*PIRATE_SHOT_SPEED,hostile=True))
                spd=math.hypot(pr.vx,pr.vy)
                if spd>PIRATE_MAX_SPEED: pr.vx*=PIRATE_MAX_SPEED/spd; pr.vy*=PIRATE_MAX_SPEED/spd
                pr.x+=pr.vx*dt; pr.y+=pr.vy*dt
                if pr.deadly and pr.partner and pr.partner in pirates and ship.invuln<=0 and not ship.immortal:
                    if dist_point_seg(ship.x,ship.y,pr.x,pr.y,pr.partner.x,pr.partner.y)<8:
                        dead,_=apply_damage(ship,PIRATE_DAMAGE)
                        if dead: game_over,rise_t=True,RESURRECT_WINDOW
                if not (scared and math.hypot(pr.x-ship.x,pr.y-ship.y)>900): live_p.append(pr)
            pirates=live_p; live_b=[]
            for b in bullets:
                b.x+=b.vx*dt; b.y+=b.vy*dt; b.life-=dt; hit=False
                if b.hostile:
                    if math.hypot(b.x-ship.x,b.y-ship.y)<ship.r+b.r or (ship.companion and math.hypot(b.x-ship.cx,b.y-ship.cy)<12+b.r):
                        dead,_=apply_damage(ship,PIRATE_DAMAGE)
                        if dead: game_over,rise_t=True,RESURRECT_WINDOW
                        hit=True
                else:
                    for p in nearby:
                        for a in p.asteroids:
                            if a.alive and a.mine and math.hypot(a.x-b.x,a.y-b.y)<a.r+b.r:
                                arm_respawn(a); hit=True; break
                        if hit: break
                    if not hit:
                        for pr in list(pirates):
                            rad=pr.r+b.r+(4 if pr.shielded and pr.shield_hits else 0)
                            if math.hypot(pr.x-b.x,pr.y-b.y)<rad:
                                hit=True
                                if pr.shielded and pr.shield_hits>0:
                                    pr.shield_hits-=1
                                    if pr.shield_hits<=0: pr.shielded=False
                                else:
                                    pr.hp-=getattr(b,"dmg",1)
                                    if pr.hp<=0:
                                        drop_loot(drops,pr.x,pr.y,rich=pr.deadly or pr.partner is not None,jackpot=pr.was_shielded)
                                        if pr.partner and pr.partner in pirates: pr.partner.partner=None
                                        if pr in pirates: pirates.remove(pr)
                                        pirate_kills+=1
                                        if pirate_kills>=scare_need:
                                            scare_t=random.uniform(SCARE_MIN,SCARE_MAX)*(1.4 if ship.jammer else 1.0)
                                            pirate_kills=0; scare_need=random.randint(2,3); space_timer=0.0
                                            for q in pirates: q.flee=True
                                            msg,msg_t=f"Pirates break off for {scare_t:.0f}s.",2.0
                                break
                if not hit and b.life>0: live_b.append(b)
            bullets=live_b; drops=[d for d in drops if d.alive]
            if mine_seeking and warn_cool<=0: warn_chan.play(warn_snd); warn_cool=1.15
            for p in nearby:
                dx,dy=ship.x-p.x,ship.y-p.y; d=math.hypot(dx,dy)
                if 0<d<p.r+ship.r:
                    nx,ny=dx/d,dy/d; ship.x,ship.y=p.x+nx*(p.r+ship.r),p.y+ny*(p.r+ship.r)
                    vn=ship.vx*nx+ship.vy*ny
                    if vn<0: ship.vx-=1.8*vn*nx; ship.vy-=1.8*vn*ny
                    if (not ship.immortal) and (not ship.armor) and ship.invuln<=0 and abs(vn)>80:
                        ship.lives-=1; ship.invuln=1.5
                        if ship.lives<=0: game_over,rise_t=True,RESURRECT_WINDOW
        if msg_t>0: msg_t-=dt
        elif not game_over: msg=""
        quotes=nearby_quotes(system_elems,drops,ship,market,loot_market)
        camx=ship.x+(cam_off_x if warp_mode else 0); camy=ship.y+(cam_off_y if warp_mode else 0)
        screen.fill((4,6,14)); view=screen.subsurface(pygame.Rect(0,0,VIEW_W,HEIGHT))
        draw_starfield(view,camx,camy)
        draw_near=[p for p in planets.values() if abs(p.x-camx)<CHUNK*1.6 and abs(p.y-camy)<CHUNK*1.6]
        for p in draw_near:
            sx,sy=world_to_screen(p.x,p.y,camx,camy)
            if -p.r<sx<VIEW_W+p.r: pygame.draw.circle(view,p.color,(int(sx),int(sy)),int(p.r))
            for a in p.asteroids:
                if not a.alive: continue
                ax,ay=world_to_screen(a.x,a.y,camx,camy)
                if -20<ax<VIEW_W+20:
                    col=(180+int(70*abs(math.sin(t*6))),30,30) if a.mine else a.color
                    pygame.draw.circle(view,col,(int(ax),int(ay)),int(a.r+(2 if a.mine else 0)))
                    if math.hypot(a.x-ship.x,a.y-ship.y)<LABEL_DIST and not a.mine:
                        view.blit(tiny.render(a.symbol,True,(240,245,255)),(ax+a.r+3,ay-a.r-8))
        for loot in drops: draw_loot_item(view,loot,camx,camy)
        for pr in pirates:
            px,py=world_to_screen(pr.x,pr.y,camx,camy)
            pygame.draw.polygon(view,(180,40,50),[(px,py-12),(px+14,py+10),(px-14,py+10)])
            if pr.shielded and pr.shield_hits>0: pygame.draw.circle(view,(80,200,255),(int(px),int(py)),18,1)
            if pr.deadly and pr.partner and pr.partner in pirates:
                qx,qy=world_to_screen(pr.partner.x,pr.partner.y,camx,camy); pygame.draw.line(view,(255,60,40),(px,py),(qx,qy),2)
        for b in bullets:
            bx,by=world_to_screen(b.x,b.y,camx,camy); pygame.draw.circle(view,b.color,(int(bx),int(by)),b.r)
        col=(255,240,210) if ship.invuln<=0 or int(ship.invuln*12)%2==0 else (255,80,80)
        if ship.immortal: col=(180,255,220)
        sx,sy=world_to_screen(ship.x,ship.y,camx,camy); draw_ship_shape(view,sx,sy,ship.ang,col)
        if ship.shield and ship.shield_hits>0: pygame.draw.circle(view,(80,180,255),(int(sx),int(sy)),int(ship.shield_r),1)
        if ship.companion:
            cx,cy=world_to_screen(ship.cx,ship.cy,camx,camy)
            pygame.draw.line(view,(120,180,220),(sx,sy),(cx,cy),1)
            draw_ship_shape(view,cx,cy,ship.ang,(180,210,230),0.72)
            if ship.shield and ship.shield_hits>0: pygame.draw.circle(view,(80,180,255),(int(cx),int(cy)),int(ship.shield_r*0.75),1)
            if ship.thrusting: pygame.draw.circle(view,(255,160,40),(int(cx+math.cos(ship.ang+math.pi)*10),int(cy+math.sin(ship.ang+math.pi)*10)),4)
        if ship.thrusting: pygame.draw.circle(view,(255,160,40),(int(sx+math.cos(ship.ang+math.pi)*14),int(sy+math.sin(ship.ang+math.pi)*14)),5)
        if not in_system and not warp_mode: draw_nav_graph(view,ship,nearby,camx,camy)
        if warp_mode: view.blit(small.render("WARP  arrows scroll  Enter/G exit",True,(180,255,220)),(20,20))
        draw_panel(screen,font,small,tiny,quotes,ship,msg,mission,t,scare_t)
        if store_open: draw_store(screen,font,small,ship,store_sel,tractor_sel,store_notice)
        if help_open: draw_help(screen,font,small,help_page)
        if offer is not None: draw_dialog(screen,font,small,offer,t,tour=show_tour,remain=show_t,mouth_on=mouth_on)
        if cheat_open: draw_cheat(screen,font,small,cheat_text)
        if game_over:
            overlay=pygame.Surface((VIEW_W,HEIGHT),pygame.SRCALPHA); overlay.fill((0,0,0,140)); view.blit(overlay,(0,0))
            g=big.render("GAME OVER",True,(255,200,180)); view.blit(g,g.get_rect(center=(VIEW_W//2,HEIGHT//2-30)))
            if ship.can_resurrect and rise_t>0:
                view.blit(small.render(f"Y to resurrect  {rise_t:.0f}s",True,(180,255,200)),(VIEW_W//2-90,HEIGHT//2+20))
            view.blit(small.render("R restart",True,(200,200,200)),(VIEW_W//2-40,HEIGHT//2+48))
        pygame.display.flip()
    pygame.quit()

if __name__=="__main__":
    main()