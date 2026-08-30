# Guida rapida

Tutto quello che serve sta in **`~/refind-mojave-desktop/`**. Aprire un terminale
e andarci:

```bash
cd ~/refind-mojave-desktop
```

---

## Cambiare sfondo

```bash
./background.py
```

Senza argomenti fa tutto lui: stampa la libreria, apre il foglio con le sei
opzioni già montate nel tema, chiede quale vuoi, genera l'anteprima a schermo
intero e **installa solo dopo la tua conferma**. Se rispondi qualcosa di diverso
da `y` non tocca niente.

Se sai già cosa vuoi, salti il giro:

```bash
./background.py 3                 # per numero
./background.py desert-skies      # per nome
```

Per vedere l'elenco senza aprire niente:

```bash
./background.py --list
```

---

## Usare una foto tua

Due modi, scegli quello che ti è più comodo.

**Al volo**, indicando il percorso:

```bash
./background.py ~/Immagini/vacanza.jpg
```

**Oppure aggiungendola alla libreria**, così resta lì e compare nell'elenco
insieme alle altre:

```bash
cp ~/Immagini/vacanza.jpg library/custom/
./background.py                   # ora c'è anche lei, in fondo
```

Va bene qualsiasi dimensione e qualsiasi proporzione: viene ritagliata al
centro a 16:9 e portata a 3840×2160. Formati accettati: jpg, png, webp, bmp.

---

## Lo scurimento

Le lastre di vetro e le scritte bianche hanno bisogno di uno sfondo
ragionevolmente scuro sotto, altrimenti si slavano. Per questo lo sfondo viene
attenuato prima di comporci sopra il resto.

```bash
./background.py 3                 # automatico (predefinito)
./background.py --darken 0 3      # foto esattamente com'è, nessuna attenuazione
./background.py --darken 45 3     # attenua del 45%
./background.py --darken 100 3    # nero pieno
```

**L'automatico** misura la luminosità media della fascia dove poggiano le lastre
e attenua finché non arriva a **30**, il livello a cui stava la foto Mojave
originale. Sotto il 5% non fa niente, perché due o tre punti percentuali non
cambiano nulla e non vale la pena toccare la foto.

`--list` ti dice, per ogni foto, quanto misura e cosa sceglierebbe l'automatico:

```
1. Mars Over Dunes
   Public domain  ·  luminance behind the tiles 31  ·  dark enough as it is
3. Desert Skies
   CC0  ·  luminance behind the tiles 107  ·  suggested --darken 72
```

Per cambiare il comportamento predefinito, in `library/library.json`:

```json
"darken_predefinito": "auto"      →  metti un numero da 0 a 100 se preferisci
```

---

## Vedere senza installare

```bash
./background.py --preview 5
```

Genera `preview.png` nella cartella e lo apre, senza toccare il menu di avvio.
Utile per provare una foto tua prima di deciderti.

---

## Se qualcosa va storto

L'installazione salva sempre una copia della configurazione precedente
sull'ESP. Per tornare indietro:

```bash
ls /boot/efi/EFI/refind/refind.conf.bak-*
sudo cp /boot/efi/EFI/refind/refind.conf.bak-XXXXXX /boot/efi/EFI/refind/refind.conf
```

E in qualunque situazione, anche col menu completamente rotto, **F12**
all'accensione apre il menu del firmware e ti fa scegliere Windows
scavalcando tutto.

---

## Cosa NON toccare senza rigenerare

Le lastre di vetro e le scritte "Windows"/"Ubuntu" sono **cotte dentro
`background.png`** a coordinate fisse, calcolate dalla matematica di layout di
rEFInd. Quindi:

- `big_icon_size` e `small_icon_size` in `refind.conf` **devono restare** 549 e 48
- se li cambi, va rigenerato tutto con `./build.py`, che ricalcola le coordinate
  e si ferma da solo se le spaziature non tornano più

Il perché di quei due numeri è spiegato nel `README.md`, sezione *Geometry*.
