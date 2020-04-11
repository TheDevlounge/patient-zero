#!/usr/bin/env python3



import datetime
import argparse
import asyncio
import discord
import random
import copy
import json
import os



PREFIX = ".pz" # Prefix for user commands.
CONFIG_FILE = "config.json" # Config file location.

# Default configuration.
DEFAULT_CONFIG = {
	"bot_token": "",
	"global_status_channel_id": None,
	"infected_role_name": "infected",
	"infected_role_colour": [164, 203, 110],
	"infection_chance": 5,
	"nearby_messages": 5,
	"initial_infected": 132185638983303168,
	"max_time_difference_seconds": 60,
	"incubation_time_seconds": 60
}



# Load the configuration file or create it if it doesn't exist.
def read_config_file():
	if not os.path.isfile(CONFIG_FILE):
		with open(CONFIG_FILE, 'w') as conf:
			conf.write(json.dumps(DEFAULT_CONFIG, indent = 4))

	with open(CONFIG_FILE, 'r') as conf:
		conf = json.load(conf)

	return conf









# Custom class to override automatically exiting and printing errors/help
# in argparse.
class ArgumentParser(argparse.ArgumentParser):
	def error(self, message):
		raise Exception(message)


	def print_help(self, *args, **kwargs):
		pass


	def parse_args(self, *args, **kwargs):
		try:
			out = super().parse_args(*args, **kwargs)

		# Catch errors.
		except Exception as e:
			return (False, str(e))

		# Catch help.
		except SystemExit as e:
			return (False, self.format_help())

		return (True, out)



# Parser for user commands.
parser = ArgumentParser(prog = ".pz", description = "A bot that simulates a rudimentary pandemic.")
actions = parser.add_mutually_exclusive_group()


actions.add_argument(
	"-i", "--infect",
	action = "store_const",
	dest = "action",
	const = "infect",
	help = "Infect a user."
)

actions.add_argument(
	"-c", "--cure",
	action = "store_const",
	dest = "action",
	const = "cure",
	help = "Cure a user."
)

actions.add_argument(
	"-r", "--reset",
	action = "store_const",
	dest = "action",
	const = "reset",
	help = "Cure everyone."
)


parser.add_argument(
	"patients",
	type = int,
	nargs = "*",
	default = "",
	help = "The users to operate on."
)









class Client(discord.Client):
	def __init__(self, config):
		super().__init__()

		self.config = config
		self.appinfo = None

		# Track users which are not yet infected but
		# which should still be ignored.
		self.incubating = set()



	def run(self):
		print("[-] Starting.")
		super().run(self.config["bot_token"])



	async def on_ready(self):
		print(f"[-] Logged in as '{self.user}'.")

		await self.change_presence(
			status = discord.Status.online, activity = discord.Game("the game of life and death")
		)

		self.appinfo = await self.application_info()



	async def on_guild_join(self, guild):
		print(f"[!] Joined a new guild: '{guild.name}'.")


		# Get infected role or create it if it doesn't exist.
		infected_role = await self.get_infected_role(guild)


		# Send an embed with some helpful information.
		embed = discord.Embed(
			title = "Setup",
			description = "Hi, thanks for adding my bot to your server. Patient Zero simulates a rudimentary epidemic by 'spreading' to other members who converse with an infected individual.",
			colour = discord.Colour.from_rgb(*self.config["infected_role_colour"])
		)


		embed.set_author(
			name = "Patient Zero",
			url = "https://discord.gg/RmgjcES",
			icon_url = "attachment://logo.png"
		)


		embed.add_field(
			name = "1. Configure role hierarchy",
			value = "You must place the bot role 'Patient Zero' above the other roles which you wish to infect. I will not have permission to add the 'infected' role to a member otherwise.",
			inline = False
		)


		embed.add_field(
			name = "2. Add the infected to role to a member",
			value = "You must add the newly created 'infected' role to at least one member who will serve as patient zero.",
			inline = False
		)


		embed.add_field(
			name = "3. Create a status channel",
			value = "The bot will send status messages inside a channel named 'pz-log' in your server. The only requirement for this channel is that it is write accessible to the bot. If no such channel exists, the bot will simply not log infections. ",
			inline = False
		)


		# Load the logo to put inside the embed.
		with open("logo.png", "rb") as logo:
			logo = discord.File(fp = logo, filename = "logo.png")


		# Send in status channel or else fall back to first available text channel.
		if guild.system_channel is not None:
			await guild.system_channel.send(embed = embed, file = logo)

		else:
			guild.text_channels[0].send(embed = embed, file = logo)



	async def get_infected_role(self, guild):
		infected_role = discord.utils.get(guild.roles, name = self.config["infected_role_name"])

		if infected_role is None:
			print("[!] Role doesn't exist in server, creating it.")

			infected_role = await guild.create_role(
				name = self.config["infected_role_name"],
				reason = "role for tracking infected.",
				colour = discord.Colour.from_rgb(*self.config["infected_role_colour"])
			)

		return infected_role



	async def on_message(self, message):
		# Make sure the message is not sent by this bot and
		# also make sure that the member is still in the guild.
		if message.author == self.user or isinstance(message.author, discord.User):
			return


		# Get infected role and check if member is infected.
		infected_role = await self.get_infected_role(message.guild)

		if infected_role not in message.author.roles:
			return


		# At this point the author is valid and infected.
		print(f"[!] Member '{message.author}' is infected, checking nearby messages.")


		# Keep track of users we've seen, this will stop multiple infections
		# to the same person.
		seen_users = { message.author.id, self.user.id }


		# Timestamp cutoff point for past messages.
		max_time_diff = message.created_at - datetime.timedelta(seconds = self.config["max_time_difference_seconds"])
		distance = 0


		# Read message history.
		async for msg in message.channel.history(limit = self.config["nearby_messages"], before = message):
			distance += 1


			# If message is too old, we skip checking any more messages.
			# We also make sure the user is still inside the guild.
			if msg.created_at < max_time_diff or isinstance(msg.author, discord.User):
				break

			# Make sure this user has not been seen previously.
			if msg.author.id in seen_users or msg.author.id in self.incubating:
				continue

			seen_users.add(msg.author.id)


			# Check if member is already infected.
			if infected_role in msg.author.roles:
				continue


			# Decide whether or not to infect this user.
			n = self.config["nearby_messages"]  # number of messages to check
			c = self.config["infection_chance"] # this will cap the infection chance at some percentage


			# Function which reduces chances of infection based on distance
			multiplier = c - (((distance / 1) / n) ** 4) * c

			print(f"\t[-] Chance of infection: {int(multiplier)}% at distance {distance}, for member '{msg.author.name}'")

			if random.randint(1, 100) <= multiplier:
				print(f"\t[!] Member {message.author.name} infected {msg.author.name}.")

				# Construct a status message to send.
				src_nick = "" if message.author.nick is None else f" ({message.author.nick})"
				dest_nick = "" if msg.author.nick is None else f" ({msg.author.nick})"

				status = f"{message.author.name}#{message.author.discriminator}{src_nick} infected {msg.author.name}#{msg.author.discriminator}{dest_nick} in '{message.guild.name}'."


				# Get global status channel and local status channel.
				global_status_channel = self.get_channel(self.config["global_status_channel_id"])
				local_status_channel = discord.utils.get(message.guild.text_channels, name = "pz-log")


				# Send new status message.
				if global_status_channel is not None:
					await global_status_channel.send(content = status)

				if local_status_channel is not None:
					await local_status_channel.send(content = status)


				# Add user to incubating set and then sleep in a non blocking way.
				self.incubating.add(msg.author.id)

				await asyncio.sleep(self.config["incubation_time_seconds"])
				await msg.author.add_roles(infected_role, reason = "this person was infected.")

				# Remove user from incubating set, they are now infected.
				if msg.author.id in self.incubating:
					self.incubating.remove(msg.author.id)

			else:
				print(f"\t[-] Not infecting '{msg.author.name}'.")

		print("\t[-] Done!")



def main():
	conf = read_config_file()

	if conf["bot_token"] == "":
		print("[!] No token defined in config.json!")
		return

	client = Client(conf)
	client.run()



if __name__ == "__main__":
	main()
