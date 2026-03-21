<<<<<<< HEAD
import discord
from discord.ext import commands
from discord import app_commands
import random
import aiohttp

import config
from utils.helpers import embed, error_embed


class Fun(commands.Cog, name="Fun"):
    """Comenzi distractive pentru comunitate."""

    def __init__(self, bot):
        self.bot = bot

    # ─── /8ball ──────────────────────────────────────────────────────────────

    @app_commands.command(name="8ball", description="Pune o întrebare mingii magice 🎱")
    @app_commands.describe(question="Întrebarea ta")
    async def eightball(self, interaction: discord.Interaction, question: str):
        responses = [
            ("🟢 Da, cu siguranță!", config.COLOR_SUCCESS),
            ("🟢 Absolut!", config.COLOR_SUCCESS),
            ("🟢 Fără îndoială!", config.COLOR_SUCCESS),
            ("🟢 Da!", config.COLOR_SUCCESS),
            ("🟢 Toate semnele spun da.", config.COLOR_SUCCESS),
            ("🟡 Răspunde neclar, încearcă din nou.", config.COLOR_WARNING),
            ("🟡 Întreabă mai târziu.", config.COLOR_WARNING),
            ("🟡 Nu pot prezice acum.", config.COLOR_WARNING),
            ("🔴 Nu te baza pe asta.", config.COLOR_ERROR),
            ("🔴 Răspunsul meu este nu.", config.COLOR_ERROR),
            ("🔴 Perspectivele nu arată bine.", config.COLOR_ERROR),
            ("🔴 Cu siguranță nu!", config.COLOR_ERROR),
        ]
        answer, color = random.choice(responses)
        e = embed(title="🎱 Mingea Magică", color=color, fields=[
            ("❓ Întrebare", question, False),
            ("🎱 Răspuns", f"**{answer}**", False),
        ])
        await interaction.response.send_message(embed=e)

    # ─── /dice ───────────────────────────────────────────────────────────────

    @app_commands.command(name="dice", description="Aruncă zaruri 🎲")
    @app_commands.describe(sides="Numărul de fețe (implicit 6)", count="Numărul de zaruri (1-10)")
    async def dice(self, interaction: discord.Interaction, sides: int = 6, count: int = 1):
        if not 2 <= sides <= 100:
            return await interaction.response.send_message(
                embed=error_embed("Zarul trebuie să aibă între 2 și 100 de fețe."), ephemeral=True
            )
        count = max(1, min(count, 10))
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)
        rolls_str = " + ".join(f"**{r}**" for r in rolls)
        await interaction.response.send_message(embed=embed(
            title="🎲 Zaruri aruncate!",
            description=f"{rolls_str} = **{total}**\n_{count}d{sides}_",
            color=config.COLOR_FUN
        ))

    # ─── /rps ────────────────────────────────────────────────────────────────

    @app_commands.command(name="rps", description="Piatră-Foarfecă-Hârtie ✊✌️🖐️")
    @app_commands.describe(choice="piatră, foarfecă sau hârtie")
    async def rps(self, interaction: discord.Interaction, choice: str):
        choices = {"piatră": "✊", "foarfecă": "✌️", "hârtie": "🖐️"}
        choice = choice.lower()
        if choice not in choices:
            return await interaction.response.send_message(
                embed=error_embed("Alege `piatră`, `foarfecă` sau `hârtie`."), ephemeral=True
            )
        bot_choice = random.choice(list(choices.keys()))
        wins = {"piatră": "foarfecă", "foarfecă": "hârtie", "hârtie": "piatră"}
        if choice == bot_choice:
            result, color = "🤝 Egalitate!", config.COLOR_WARNING
        elif wins[choice] == bot_choice:
            result, color = "🎉 Ai câștigat!", config.COLOR_SUCCESS
        else:
            result, color = "😢 Ai pierdut!", config.COLOR_ERROR
        await interaction.response.send_message(embed=embed(
            title="✊ Piatră-Foarfecă-Hârtie",
            color=color,
            fields=[
                ("Tu", f"{choices[choice]} {choice.capitalize()}", True),
                ("Bot", f"{choices[bot_choice]} {bot_choice.capitalize()}", True),
                ("Rezultat", f"**{result}**", False),
            ]
        ))

    # ─── /guess ──────────────────────────────────────────────────────────────

    @app_commands.command(name="guess", description="Joc de ghicire a numărului (1-100)")
    async def guess(self, interaction: discord.Interaction):
        secret = random.randint(1, 100)
        await interaction.response.send_message(embed=embed(
            title="🔢 Ghicește numărul!",
            description="Am ales un număr între **1** și **100**.\nScrie numărul tău în chat!\n*(Ai 30 secunde și 5 încercări)*",
            color=config.COLOR_FUN
        ))

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel and m.content.isdigit()

        attempts = 5
        for attempt in range(1, attempts + 1):
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30.0)
            except Exception:
                return await interaction.followup.send(embed=error_embed(
                    f"Timp expirat! Numărul era **{secret}**."
                ))
            guess = int(msg.content)
            if guess == secret:
                return await interaction.followup.send(embed=embed(
                    title="🎉 Corect!",
                    description=f"Ai ghicit numărul **{secret}** în {attempt} încercări!",
                    color=config.COLOR_SUCCESS
                ))
            hint = "📈 Mai mare!" if guess < secret else "📉 Mai mic!"
            remaining = attempts - attempt
            if remaining > 0:
                await interaction.followup.send(embed=embed(
                    title=hint,
                    description=f"Îți mai rămân **{remaining}** încercări.",
                    color=config.COLOR_WARNING
                ))
        await interaction.followup.send(embed=error_embed(
            f"Ai epuizat toate încercările! Numărul era **{secret}**."
        ))

    # ─── /trivia ─────────────────────────────────────────────────────────────

    @app_commands.command(name="trivia", description="O întrebare trivia aleatorie")
    async def trivia(self, interaction: discord.Interaction):
        questions = [
            ("Ce limbaj de programare a creat Discord?", ["Python", "JavaScript", "Go", "Rust"], 0),
            ("Câte continente are Pământul?", ["5", "6", "7", "8"], 2),
            ("Care este cel mai rapid animal de uscat?", ["Leu", "Ghepard", "Cal", "Căprioară"], 1),
            ("Câte culori are curcubeul?", ["5", "6", "7", "8"], 2),
            ("Care este capitala Franței?", ["Londra", "Berlin", "Paris", "Madrid"], 2),
            ("Cine a inventat telefonul?", ["Edison", "Bell", "Tesla", "Marconi"], 1),
            ("Care este cel mai mare ocean?", ["Atlantic", "Indian", "Pacific", "Arctic"], 2),
            ("Câți bytes are un kilobyte?", ["512", "1000", "1024", "2048"], 2),
        ]
        q, options, correct_idx = random.choice(questions)
        emoji_options = ["🇦", "🇧", "🇨", "🇩"]
        choices_text = "\n".join(f"{emoji_options[i]} {opt}" for i, opt in enumerate(options))
        e = embed(
            title="🧠 Trivia!",
            description=f"**{q}**\n\n{choices_text}",
            color=config.COLOR_FUN
        )
        e.set_footer(text="Reacționează cu emoji-ul corespunzător răspunsului tău!")
        msg = await interaction.response.send_message(embed=e)
        msg_obj = await interaction.original_response()
        for em in emoji_options:
            await msg_obj.add_reaction(em)

        def check(reaction, user):
            return (
                user == interaction.user
                and str(reaction.emoji) in emoji_options
                and reaction.message.id == msg_obj.id
            )

        try:
            reaction, _ = await self.bot.wait_for("reaction_add", check=check, timeout=20.0)
            chosen = emoji_options.index(str(reaction.emoji))
            if chosen == correct_idx:
                await interaction.followup.send(embed=embed(
                    title="✅ Răspuns corect!",
                    description=f"**{options[correct_idx]}** era răspunsul corect! Bravo!",
                    color=config.COLOR_SUCCESS
                ))
            else:
                await interaction.followup.send(embed=embed(
                    title="❌ Răspuns greșit!",
                    description=f"Răspunsul corect era: **{options[correct_idx]}**",
                    color=config.COLOR_ERROR
                ))
        except Exception:
            await interaction.followup.send(embed=error_embed(
                f"Timp expirat! Răspunsul era: **{options[correct_idx]}**"
            ))

    # ─── /avatar ─────────────────────────────────────────────────────────────

    @app_commands.command(name="avatar", description="Afișează avatarul unui utilizator")
    @app_commands.describe(member="Utilizatorul (opțional)")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        e = embed(
            title=f"🖼️ Avatar — {target.display_name}",
            color=config.COLOR_PRIMARY,
            image=target.display_avatar.with_size(1024).url
        )
        await interaction.response.send_message(embed=e)

    # ─── /meme ───────────────────────────────────────────────────────────────

    @app_commands.command(name="meme", description="Un meme random de pe Reddit 😂")
    async def meme(self, interaction: discord.Interaction):
        await interaction.response.defer()
        subreddits = ["memes", "dankmemes", "programmerhumor", "gaming"]
        sub = random.choice(subreddits)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://www.reddit.com/r/{sub}/hot.json?limit=50",
                    headers={"User-Agent": "GDPBot/1.0"}
                ) as resp:
                    data = await resp.json()
            posts = [
                p["data"] for p in data["data"]["children"]
                if not p["data"]["is_self"]
                and not p["data"].get("over_18", False)
                and p["data"].get("url", "").endswith((".jpg", ".png", ".gif", ".jpeg"))
            ]
            if not posts:
                raise ValueError("No valid posts")
            post = random.choice(posts[:20])
            e = embed(
                title=post["title"][:250],
                color=config.COLOR_FUN,
                image=post["url"]
            )
            e.set_footer(text=f"r/{sub} • 👍 {post['ups']:,}")
            await interaction.followup.send(embed=e)
        except Exception:
            await interaction.followup.send(embed=error_embed("Nu am putut obține un meme acum. Încearcă din nou!"))

    # ─── /joke ───────────────────────────────────────────────────────────────

    @app_commands.command(name="joke", description="O glumă random 😄")
    async def joke(self, interaction: discord.Interaction):
        jokes = [
            ("De ce nu fac programatorii sport?", "Pentru că au deja loop-uri infinite."),
            ("Ce a zis null lui undefined?", "Nu te văd."),
            ("De ce pisicile nu joacă poker?", "Pentru că au prea mulți pui."),
            ("Câți programatori trebuie să schimbe un bec?", "Niciunul, e o problemă hardware."),
            ("De ce a traversat puiul strada?", "Ca să ajungă la cealaltă parte (dark side)."),
            ("Ce este un debug?", "Un bug care nu s-a găsit încă."),
            ("De ce dev-ii preferă dark mode?", "Pentru că lumina atrage bug-uri."),
        ]
        setup, punchline = random.choice(jokes)
        await interaction.response.send_message(embed=embed(
            title="😄 Glumă",
            color=config.COLOR_FUN,
            fields=[
                ("Setup", setup, False),
                ("Punchline", f"||{punchline}||", False),
            ]
        ))

    # ─── /poll ───────────────────────────────────────────────────────────────

    @app_commands.command(name="poll", description="Creează un sondaj cu opțiuni")
    @app_commands.describe(
        question="Întrebarea sondajului",
        option1="Prima opțiune",
        option2="A doua opțiune",
        option3="Opțional - a treia opțiune",
        option4="Opțional - a patra opțiune",
    )
    async def poll(self, interaction: discord.Interaction,
                   question: str, option1: str, option2: str,
                   option3: str = None, option4: str = None):
        options = [option1, option2]
        if option3:
            options.append(option3)
        if option4:
            options.append(option4)
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        desc = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))
        e = embed(
            title=f"📊 {question}",
            description=desc,
            color=config.COLOR_PRIMARY
        )
        e.set_footer(text=f"Votat de {interaction.user.display_name}")
        await interaction.response.send_message(embed=e)
        msg = await interaction.original_response()
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])


async def setup(bot):
    await bot.add_cog(Fun(bot))
=======
import discord
from discord.ext import commands
from discord import app_commands
import random
import aiohttp

import config
from utils.helpers import embed, error_embed


class Fun(commands.Cog, name="Fun"):
    """Comenzi distractive pentru comunitate."""

    def __init__(self, bot):
        self.bot = bot

    # ─── /8ball ──────────────────────────────────────────────────────────────

    @app_commands.command(name="8ball", description="Pune o întrebare mingii magice 🎱")
    @app_commands.describe(question="Întrebarea ta")
    async def eightball(self, interaction: discord.Interaction, question: str):
        responses = [
            ("🟢 Da, cu siguranță!", config.COLOR_SUCCESS),
            ("🟢 Absolut!", config.COLOR_SUCCESS),
            ("🟢 Fără îndoială!", config.COLOR_SUCCESS),
            ("🟢 Da!", config.COLOR_SUCCESS),
            ("🟢 Toate semnele spun da.", config.COLOR_SUCCESS),
            ("🟡 Răspunde neclar, încearcă din nou.", config.COLOR_WARNING),
            ("🟡 Întreabă mai târziu.", config.COLOR_WARNING),
            ("🟡 Nu pot prezice acum.", config.COLOR_WARNING),
            ("🔴 Nu te baza pe asta.", config.COLOR_ERROR),
            ("🔴 Răspunsul meu este nu.", config.COLOR_ERROR),
            ("🔴 Perspectivele nu arată bine.", config.COLOR_ERROR),
            ("🔴 Cu siguranță nu!", config.COLOR_ERROR),
        ]
        answer, color = random.choice(responses)
        e = embed(title="🎱 Mingea Magică", color=color, fields=[
            ("❓ Întrebare", question, False),
            ("🎱 Răspuns", f"**{answer}**", False),
        ])
        await interaction.response.send_message(embed=e)

    # ─── /dice ───────────────────────────────────────────────────────────────

    @app_commands.command(name="dice", description="Aruncă zaruri 🎲")
    @app_commands.describe(sides="Numărul de fețe (implicit 6)", count="Numărul de zaruri (1-10)")
    async def dice(self, interaction: discord.Interaction, sides: int = 6, count: int = 1):
        if not 2 <= sides <= 100:
            return await interaction.response.send_message(
                embed=error_embed("Zarul trebuie să aibă între 2 și 100 de fețe."), ephemeral=True
            )
        count = max(1, min(count, 10))
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)
        rolls_str = " + ".join(f"**{r}**" for r in rolls)
        await interaction.response.send_message(embed=embed(
            title="🎲 Zaruri aruncate!",
            description=f"{rolls_str} = **{total}**\n_{count}d{sides}_",
            color=config.COLOR_FUN
        ))

    # ─── /rps ────────────────────────────────────────────────────────────────

    @app_commands.command(name="rps", description="Piatră-Foarfecă-Hârtie ✊✌️🖐️")
    @app_commands.describe(choice="piatră, foarfecă sau hârtie")
    async def rps(self, interaction: discord.Interaction, choice: str):
        choices = {"piatră": "✊", "foarfecă": "✌️", "hârtie": "🖐️"}
        choice = choice.lower()
        if choice not in choices:
            return await interaction.response.send_message(
                embed=error_embed("Alege `piatră`, `foarfecă` sau `hârtie`."), ephemeral=True
            )
        bot_choice = random.choice(list(choices.keys()))
        wins = {"piatră": "foarfecă", "foarfecă": "hârtie", "hârtie": "piatră"}
        if choice == bot_choice:
            result, color = "🤝 Egalitate!", config.COLOR_WARNING
        elif wins[choice] == bot_choice:
            result, color = "🎉 Ai câștigat!", config.COLOR_SUCCESS
        else:
            result, color = "😢 Ai pierdut!", config.COLOR_ERROR
        await interaction.response.send_message(embed=embed(
            title="✊ Piatră-Foarfecă-Hârtie",
            color=color,
            fields=[
                ("Tu", f"{choices[choice]} {choice.capitalize()}", True),
                ("Bot", f"{choices[bot_choice]} {bot_choice.capitalize()}", True),
                ("Rezultat", f"**{result}**", False),
            ]
        ))

    # ─── /guess ──────────────────────────────────────────────────────────────

    @app_commands.command(name="guess", description="Joc de ghicire a numărului (1-100)")
    async def guess(self, interaction: discord.Interaction):
        secret = random.randint(1, 100)
        await interaction.response.send_message(embed=embed(
            title="🔢 Ghicește numărul!",
            description="Am ales un număr între **1** și **100**.\nScrie numărul tău în chat!\n*(Ai 30 secunde și 5 încercări)*",
            color=config.COLOR_FUN
        ))

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel and m.content.isdigit()

        attempts = 5
        for attempt in range(1, attempts + 1):
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30.0)
            except Exception:
                return await interaction.followup.send(embed=error_embed(
                    f"Timp expirat! Numărul era **{secret}**."
                ))
            guess = int(msg.content)
            if guess == secret:
                return await interaction.followup.send(embed=embed(
                    title="🎉 Corect!",
                    description=f"Ai ghicit numărul **{secret}** în {attempt} încercări!",
                    color=config.COLOR_SUCCESS
                ))
            hint = "📈 Mai mare!" if guess < secret else "📉 Mai mic!"
            remaining = attempts - attempt
            if remaining > 0:
                await interaction.followup.send(embed=embed(
                    title=hint,
                    description=f"Îți mai rămân **{remaining}** încercări.",
                    color=config.COLOR_WARNING
                ))
        await interaction.followup.send(embed=error_embed(
            f"Ai epuizat toate încercările! Numărul era **{secret}**."
        ))

    # ─── /trivia ─────────────────────────────────────────────────────────────

    @app_commands.command(name="trivia", description="O întrebare trivia aleatorie")
    async def trivia(self, interaction: discord.Interaction):
        questions = [
            ("Ce limbaj de programare a creat Discord?", ["Python", "JavaScript", "Go", "Rust"], 0),
            ("Câte continente are Pământul?", ["5", "6", "7", "8"], 2),
            ("Care este cel mai rapid animal de uscat?", ["Leu", "Ghepard", "Cal", "Căprioară"], 1),
            ("Câte culori are curcubeul?", ["5", "6", "7", "8"], 2),
            ("Care este capitala Franței?", ["Londra", "Berlin", "Paris", "Madrid"], 2),
            ("Cine a inventat telefonul?", ["Edison", "Bell", "Tesla", "Marconi"], 1),
            ("Care este cel mai mare ocean?", ["Atlantic", "Indian", "Pacific", "Arctic"], 2),
            ("Câți bytes are un kilobyte?", ["512", "1000", "1024", "2048"], 2),
        ]
        q, options, correct_idx = random.choice(questions)
        emoji_options = ["🇦", "🇧", "🇨", "🇩"]
        choices_text = "\n".join(f"{emoji_options[i]} {opt}" for i, opt in enumerate(options))
        e = embed(
            title="🧠 Trivia!",
            description=f"**{q}**\n\n{choices_text}",
            color=config.COLOR_FUN
        )
        e.set_footer(text="Reacționează cu emoji-ul corespunzător răspunsului tău!")
        msg = await interaction.response.send_message(embed=e)
        msg_obj = await interaction.original_response()
        for em in emoji_options:
            await msg_obj.add_reaction(em)

        def check(reaction, user):
            return (
                user == interaction.user
                and str(reaction.emoji) in emoji_options
                and reaction.message.id == msg_obj.id
            )

        try:
            reaction, _ = await self.bot.wait_for("reaction_add", check=check, timeout=20.0)
            chosen = emoji_options.index(str(reaction.emoji))
            if chosen == correct_idx:
                await interaction.followup.send(embed=embed(
                    title="✅ Răspuns corect!",
                    description=f"**{options[correct_idx]}** era răspunsul corect! Bravo!",
                    color=config.COLOR_SUCCESS
                ))
            else:
                await interaction.followup.send(embed=embed(
                    title="❌ Răspuns greșit!",
                    description=f"Răspunsul corect era: **{options[correct_idx]}**",
                    color=config.COLOR_ERROR
                ))
        except Exception:
            await interaction.followup.send(embed=error_embed(
                f"Timp expirat! Răspunsul era: **{options[correct_idx]}**"
            ))

    # ─── /avatar ─────────────────────────────────────────────────────────────

    @app_commands.command(name="avatar", description="Afișează avatarul unui utilizator")
    @app_commands.describe(member="Utilizatorul (opțional)")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        e = embed(
            title=f"🖼️ Avatar — {target.display_name}",
            color=config.COLOR_PRIMARY,
            image=target.display_avatar.with_size(1024).url
        )
        await interaction.response.send_message(embed=e)

    # ─── /meme ───────────────────────────────────────────────────────────────

    @app_commands.command(name="meme", description="Un meme random de pe Reddit 😂")
    async def meme(self, interaction: discord.Interaction):
        await interaction.response.defer()
        subreddits = ["memes", "dankmemes", "programmerhumor", "gaming"]
        sub = random.choice(subreddits)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://www.reddit.com/r/{sub}/hot.json?limit=50",
                    headers={"User-Agent": "GDPBot/1.0"}
                ) as resp:
                    data = await resp.json()
            posts = [
                p["data"] for p in data["data"]["children"]
                if not p["data"]["is_self"]
                and not p["data"].get("over_18", False)
                and p["data"].get("url", "").endswith((".jpg", ".png", ".gif", ".jpeg"))
            ]
            if not posts:
                raise ValueError("No valid posts")
            post = random.choice(posts[:20])
            e = embed(
                title=post["title"][:250],
                color=config.COLOR_FUN,
                image=post["url"]
            )
            e.set_footer(text=f"r/{sub} • 👍 {post['ups']:,}")
            await interaction.followup.send(embed=e)
        except Exception:
            await interaction.followup.send(embed=error_embed("Nu am putut obține un meme acum. Încearcă din nou!"))

    # ─── /joke ───────────────────────────────────────────────────────────────

    @app_commands.command(name="joke", description="O glumă random 😄")
    async def joke(self, interaction: discord.Interaction):
        jokes = [
            ("De ce nu fac programatorii sport?", "Pentru că au deja loop-uri infinite."),
            ("Ce a zis null lui undefined?", "Nu te văd."),
            ("De ce pisicile nu joacă poker?", "Pentru că au prea mulți pui."),
            ("Câți programatori trebuie să schimbe un bec?", "Niciunul, e o problemă hardware."),
            ("De ce a traversat puiul strada?", "Ca să ajungă la cealaltă parte (dark side)."),
            ("Ce este un debug?", "Un bug care nu s-a găsit încă."),
            ("De ce dev-ii preferă dark mode?", "Pentru că lumina atrage bug-uri."),
        ]
        setup, punchline = random.choice(jokes)
        await interaction.response.send_message(embed=embed(
            title="😄 Glumă",
            color=config.COLOR_FUN,
            fields=[
                ("Setup", setup, False),
                ("Punchline", f"||{punchline}||", False),
            ]
        ))

    # ─── /poll ───────────────────────────────────────────────────────────────

    @app_commands.command(name="poll", description="Creează un sondaj cu opțiuni")
    @app_commands.describe(
        question="Întrebarea sondajului",
        option1="Prima opțiune",
        option2="A doua opțiune",
        option3="Opțional - a treia opțiune",
        option4="Opțional - a patra opțiune",
    )
    async def poll(self, interaction: discord.Interaction,
                   question: str, option1: str, option2: str,
                   option3: str = None, option4: str = None):
        options = [option1, option2]
        if option3:
            options.append(option3)
        if option4:
            options.append(option4)
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        desc = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))
        e = embed(
            title=f"📊 {question}",
            description=desc,
            color=config.COLOR_PRIMARY
        )
        e.set_footer(text=f"Votat de {interaction.user.display_name}")
        await interaction.response.send_message(embed=e)
        msg = await interaction.original_response()
        for i in range(len(options)):
            await msg.add_reaction(emojis[i])


async def setup(bot):
    await bot.add_cog(Fun(bot))
>>>>>>> 84b633404fd2d5a084c32e7232431219eb31d7f5
