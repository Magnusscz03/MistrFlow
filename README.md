# MistrFlow — obnovení webu na Vercelu a Supabase

Produkce: https://mistrflow.vercel.app/
Supabase: dxpzqepbkkhcbpqmnokn. Floot se nepoužívá.

## Obsah

- `dist/`: kompletní statická verze pro nasazení, veřejná nabídka, ceník, formulář a původní aplikace.
- `dist/app/`: obnovená aplikace s přihlášením, zakázkami, zákazníky, kalendářem, ceníkem, fakturami, financemi a správou platformy.
- `backend/`: nasazené Edge Functions pro zájemce, checkout, administraci, Stripe webhook a stav nepřipojené Owner AI.
- `migrations/`: SQL nové tabulky zájemců a veřejného katalogu cen.
- `deployment-manifest.json`: všechny soubory konkrétní nasazované verze, velikost a SHA-1.
- `android-release.json`: kontrolovaný záznam verze, odkazu, velikosti, SHA-256 a cílové adresy Android aplikace.
- `dist/connectivity.js` a `dist/connectivity.css`: nezávislé upozornění na ztrátu a obnovení připojení v aplikaci a intake formuláři.
- `dist/icon-192.png`, `dist/icon-512.png` a `dist/icon-maskable-512.png`: standardní ikony webové aplikace pro instalaci z podporovaného mobilního prohlížeče.
- `scripts/audit_supabase_security.sql`: čistě čtecí kontrola RLS, politik, privilegovaných funkcí a view dostupných přes API; správný výsledek je nula řádků.
- `scripts/audit_supabase_data_api_access.sql`: čistě čtecí kontrola explicitního kontraktu Data API pro veřejný ceník, Android releases a základní přihlášené moduly; správný výsledek je nula řádků.

Původní aplikace byla obnovena z funkčního dřívějšího nasazení jako zkompilovaný JavaScript. Toto není původní editovatelný React/Next zdrojový projekt. Nové veřejné stránky a Edge Functions mají editovatelný zdroj přímo v tomto balíčku. Zápis do GitHubu byl 8. října 2026 obnoven. Tento projekt se přenáší do pracovní větve `codex/mistrflow-release-20261008-0918`; stav nasazení musí být ověřen samostatně.

## Nasazování

Nasazujte vždy CELÝ obsah `dist/`, nikoliv jen změněné soubory. Předchozí částečná nasazení odstranila z webu zbytek aplikace. `vercel.json` obsahuje přesměrování Edge Functions do Supabase; backend se nasazuje samostatně do uvedeného Supabase projektu.

Při nasazení z kořene repozitáře použijte konfiguraci kořenového `vercel.json`: framework Other, výstup `dist`, kontrolní build `node scripts/verify-deploy.mjs` a prázdný install příkaz. Obnovené assets jsou pod `_next/static/restored-v1/`, protože původní immutable cesty nesmějí pod stejným názvem změnit obsah. Service worker odstraní staré MistrFlow cache a nepoužívá zastaralý offline shell.

Před nasazením spusťte `python3 scripts/verify_release.py`. Stažené APK ověřte příkazem `python3 scripts/verify_apk.py cesta/k/MistrFlow-0.1.1-debug.apk`; kontrola porovná velikost a SHA-256 a uvnitř APK prověří identitu aplikace, produkční HTTPS adresu i zákaz nezabezpečeného a smíšeného obsahu. Po kompletním produkčním nasazení spusťte `python3 scripts/verify_production.py` a `python3 scripts/verify_security_headers.py`. Produkční kontrola vyžaduje `/`, `/intake` a `/download` = 200, neautorizovaný `POST /api/owner-ai` = 401 a ověřuje metadata Android vydání. Druhá kontrola hlídá HSTS, zákaz MIME sniffingu, vložení webu do cizího rámce a bezpečné předávání referreru na všech veřejných vstupních stránkách. Při chybě deployment nepropagujte; pokud selže kořenová stránka, vraťte poslední kompletní funkční deployment.

Frontend obsahuje jen veřejný publishable key. Service role, Stripe a další tajné klíče patří do prostředí Edge Functions nebo Supabase Vault; nejsou v balíčku.

Audit Supabase spusťte v SQL editoru cílového projektu obsahem `scripts/audit_supabase_security.sql`. Nulový výsledek znamená, že audit nenašel veřejnou tabulku bez RLS, politiku založenou na uživatelsky měnitelných metadatech, veřejně spustitelnou `SECURITY DEFINER` funkci ani API view bez `security_invoker`. Audit nenahrazuje test dvou skutečných tenantů a nic v databázi nemění.

Před a po každé migraci spusťte také `scripts/audit_supabase_data_api_access.sql`. Kontrola zahrnuje i sloupcový `GRANT` veřejného ceníku, veřejné čtení mobilního release záznamu, zákaz anonymního čtení zákazníků a poptávek a čtení hlavních modulů přihlášeným uživatelem. Je připravená na vypnutí automatického zpřístupnění nových tabulek přes Supabase Data API dne 30. října 2026. Nulový výsledek potvrzuje oprávnění a zákazy, nikoliv správnost RLS pro jednotlivé tenanty.

Mobilní aplikace a formulář `/intake` při ztrátě internetu zobrazí výrazné upozornění, že nové změny se neuloží. Po obnovení připojení zobrazí krátké potvrzení. Úprava nepředstírá offline synchronizaci a nemění zkompilovanou aplikační logiku.

Webový manifest nyní nabízí stabilní identitu `/app`, český jazyk, rozsah celé instalace, běžné PNG ikony 192 × 192 a 512 × 512 a samostatnou maskovatelnou ikonu. Nainstalovaná webová aplikace může nabídnout zástupce pro otevření aplikace a poptávkového formuláře. To zlepšuje mobilní používání, ale nenahrazuje samostatné podepsané APK/AAB ani distribuci nové nativní verze.

## Historické ověření původního nasazení (nepotvrzuje aktuální produkci)

- Produkční stránka a registrační obrazovka se načítají v prohlížeči.
- Ceník načítá veřejné aktivní plány Supabase; funguje přepnutí měsíčních a ročních cen.
- Formulář přes produkční Vercel proxy vrací 200 a ukládá skutečný záznam do Supabase. Testovací záznam byl následně odstraněn.
- Neplatný formulář vrací 400, checkout bez přihlášení 401.
- Anonymní návštěvník nemá právo číst customers ani sales_inquiries.
- Test v SQL transakci ověřil, že vznik běžného uživatele vytvoří jeho organizaci, vlastníka a zkušební předplatné; uživatel vidí svou organizaci, nikoliv cizí organizace nebo zájemce platformy. Celý test byl vrácen rollbackem.

Přihlášení reálného uživatele, doručení potvrzovacího e-mailu a celý pracovní tok pod jeho účtem nebyly ověřeny. Nebyly provedeny skutečné platby, rozesílání SMS ani odpovědi AI.

## Co zbývá před placeným prodejem

1. Připojit vlastní Stripe účet: secret key a podpisový webhook secret do Vault. Webhook musí přijímat relevantní subscription události na Supabase `stripe-webhook`. Ověřit testovací checkout, webhook, zrušení a změnu předplatného, teprve potom přepnout na živé klíče. Klíče nevkládat do veřejného frontendu ani do chatu.
2. Doplnit skutečné identifikační a kontaktní údaje provozovatele, daňové údaje, obchodní podmínky a úplné zásady soukromí. Tyto údaje nebyly v dostupném projektu doložené.
3. Pro aktivní SMS připojit poskytovatele a klíč; pro skutečnou AI dodat a implementovat připojení poskytovatele. Owner AI nyní bezpečně vrací informaci o nepřipojené službě, nic nevymýšlí ani nemění.
4. Android 0.1.1 je debug sestavení pro interní testování. Připravit podepsané produkční vydání, pokud se má distribuovat veřejně jako hotová mobilní aplikace.

Web již může přijímat registrace a nezávazné zájemce. Checkout je připravený a má ověřování uživatele i vlastníka organizace, serverové ceny a podpisový webhook. Bez chybějících Stripe klíčů vrací 503 a žádnou platbu neprovede. Návratová URL nezvyšuje oprávnění a nepřepíná tarif na zaplacený.

## Připravená úprava 7. října 2026 — NEZVEŘEJNĚNO

Stránka /download má sjednocený vzhled, návod k instalaci, správný SHA-256 APK 0.1.1 a vysvětlení aktualizací. Výslovně upozorňuje uživatele verze 0.1.0, že ji kvůli odlišnému testovacímu podpisu musí před instalací 0.1.1 odinstalovat. Přidány samostatné kontroly produkce a APK, upozornění na stav připojení v aplikaci a intake formuláři a standardní PNG ikony webové aplikace včetně maskovatelné varianty. Ověřené APK má ID `cz.mistrflow.app`, načítá `https://mistrflow.vercel.app`, nepovoluje nezabezpečené HTTP ani smíšený obsah a odpovídá aktivnímu záznamu v Supabase. Původní http-verification.json popisuje starší vydání. GitHub zápis a Vercel přístup stále vracejí 403.

## Logo — 8. října 2026 (připraveno, nezveřejněno)

Jednotné logo je zapojeno do všech sedmi HTML stránek, sdílené značky na přihlášení a v aplikaci pomocí brand.css, favicon, Apple touch icon, PWA ikon a metadat pro sdílení. Android launcher podklady jsou v brand/android-launcher-source; existující APK není změněné. Podrobnosti a prompt jsou v brand/README.md. Ověřena úplnost 37 distribučních souborů a odkazy ve všech HTML. Vzhled v přihlášené produkční aplikaci ani nový APK nebyly ověřeny.

Kontrola release navíc automaticky hlídá rozměry čtyř hlavních značkových PNG, jejich metadata na všech HTML stránkách a propojení značky se sdílenou hlavičkou obnovené aplikace. Tím se zabrání tichému návratu staré ikony nebo chybějícímu logu při příštím kompletním sestavení.

## Nasazení z kořene Git repozitáře — připraveno 8. října

Kořenový vercel.json vybírá statický adresář dist a zachovává přesměrování do Supabase i bezpečnostní hlavičky. Kontrolní build `node scripts/verify-deploy.mjs` bez externích závislostí odmítne neúplný nebo změněný manifest. Backend Edge Functions se tímto krokem nenasazuje.

Obsah adresáře MistrFlow patří do kořene repozitáře, nikoli do další vnořené složky. Root Directory na Vercelu musí odpovídat tomuto kořeni. Před propojením produkční větve je nutné ověřit kompletní obsah a náhled. .gitignore vylučuje lokální klíče, .env a podpisové soubory; nejde o plnohodnotnou kontrolu uniklých secrets.

Stav této úpravy: pouze uložená příprava, GitHub vytvoření větve i Vercel čtení projektu nadále vrací 403. Nové nasazení ani Android sestavení neproběhlo.

## PWA cache a kontrola nasazení — 8. října 2026 (v13, nezveřejněno)

Service worker ukládá jen osm výslovně povolených veřejných ikon a manifest. Nikdy neobsluhuje navigace, API, přihlášení ani data zákazníků. Hlavní `verify_release.py` tuto hranici nyní kontroluje přímo, takže bezpečnost cache už nezávisí na spuštění samostatného pomocného skriptu. Produkční kontrola bezpečnostních hlaviček navíc vyžaduje pro `/sw.js` stav 200 a `Cache-Control: no-store`, aby prohlížeče rychle získaly novou verzi pracovníka.

## Přenos do GitHubu — 8. října 2026

Obnoveno z archivu v13. Starší zmínky o GitHub 403 výše jsou historické; vytvoření pracovní větve již uspělo. Vercel API stále odmítá přístup k týmu a nové produkční nasazení není potvrzené. `http-verification.json` a `nahled.jpg` jsou historické podklady, nikoli důkaz dnešního stavu.

Před commitem se ověřuje úplnost distribučních souborů, shoda konfigurace a zákaz ukládání soukromých dat do PWA cache. Původní editovatelný React projekt, produkční Android podpis a připojení SMS, telefonování, AI a plateb zůstávají samostatnými nedokončenými úkoly.


## Editovatelný Next.js základ z větve main

Souběžná práce na `main` přidala minimální editovatelný Next.js základ (`app/`, `package.json`, `tsconfig.json` a `.env.example`). Tyto soubory jsou v pracovní větvi zachované, ale aktuální Vercel konfigurace záměrně dál publikuje kompletní ověřený adresář `dist/`. Jednoduchá stránka z `app/page.tsx` proto nenahrazuje obnovenou aplikaci a není produkčním vstupem.

Další vývoj má postupně převést funkce z obnoveného zkompilovaného JavaScriptu do editovatelných React komponent při zachování stejného Supabase projektu, tenantního modelu a veřejných tras. Přepnutí Vercelu na Next.js je samostatný release krok až po úplném funkčním a bezpečnostním ověření.
