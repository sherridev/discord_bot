import discord
from discord.ext import commands
from datetime import datetime, timedelta
import pytz
import pandas as pd
import os
from fuzzywuzzy import fuzz, process  # Import fuzzywuzzy for fuzzy string matching

# Bot setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory data storage for user records
user_data = {}

# Initialize pandas DataFrame to track attendance data
columns = ["Employee Name", "Check-In Date", "Check-In Time", "Check-Out Date", "Check-Out Time", "Total Break Time (hh:mm:ss)", "Total Time Worked (hh:mm:ss)", "Total Break-Ins"]
attendance_df = pd.DataFrame(columns=columns)

# Directory and file for saving attendance data
attendance_file_path = "attendance_data.csv"

# Time zone setup
local_timezone = pytz.timezone('Asia/Karachi')

# Convert UTC to local time
def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=pytz.utc).astimezone(local_timezone)

# Helper function to calculate time difference in seconds
def calculate_time_difference(start, end, return_minutes=False):
    difference = (end - start).total_seconds()  # This will give the time difference in seconds
    if return_minutes:
        return difference / 60  # Return in minutes
    return difference  # Return in seconds by default

# Convert seconds to hh:mm:ss format
def seconds_to_hms(seconds):
    return str(timedelta(seconds=seconds))

# Save DataFrame to CSV
def save_attendance_data():
    if not attendance_df.empty:
        attendance_df.to_csv(attendance_file_path, index=False)
        print(f"Attendance data saved to {attendance_file_path}")
    else:
        print("No data to save.")

# Fuzzy matching function to check if message contains any relevant command
def fuzzy_match_command(content, command_list):
    matched_command = process.extractOne(content, command_list, scorer=fuzz.partial_ratio)
    return matched_command[0] if matched_command and matched_command[1] > 80 else None

# Event: When the bot is ready
@bot.event
async def on_ready():
    print(f"Bot is online! Logged in as {bot.user}")

    # Load existing attendance data from CSV (if any)
    if os.path.exists(attendance_file_path):
        global attendance_df
        attendance_df = pd.read_csv(attendance_file_path)
        print("Attendance data loaded.")

# Event: On message
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    channel = message.channel
    user = message.author
    content = message.content.lower()
    timestamp = message.created_at

    if channel.name != "main":  # Ensure messages are only processed in the "main" channel
        return

    if user.id not in user_data:
        user_data[user.id] = {
            "check_in": None,
            "check_out": None,
            "break_start": None,
            "total_break_time": 0,  # Track total break time in seconds
            "total_break_ins": 0,   # Track the total number of break-ins
        }

    user_record = user_data[user.id]

    # List of valid commands for fuzzy matching
    valid_commands = ["check in", "check out", "break in", "break out"]

    # Try to match the command with fuzzy matching
    matched_command = fuzzy_match_command(content, valid_commands)

    if matched_command == "check in":
        if user_record["check_in"]:
            if user_record["check_out"]:
                # Check if the user has previously checked out. If so, treat this as a new check-in.
                # Mark previous check-out as complete and start a new row for check-in
                user_record["check_in"] = timestamp
                user_record["check_out"] = None
                user_record["break_start"] = None
                user_record["total_break_time"] = 0
                user_record["total_break_ins"] = 0
                local_time = utc_to_local(timestamp)
                check_in_date = local_time.strftime('%Y-%m-%d')  # Get the check-in date
                check_in_time = local_time.strftime('%H:%M:%S')  # Get the check-in time
                # await channel.send(f"{user.mention} checked in again at {check_in_time} on {check_in_date}. New session started.")

                # Create a new row after the check-out
                attendance_df.loc[len(attendance_df)] = [user.name, check_in_date, check_in_time, None, None,
                                                         "00:00:00", None, 0]
                save_attendance_data()
            else:
                await channel.send(f"{user.mention}, you are already checked in!")
        else:
            # First-time check-in (after user has not checked in previously)
            user_record["check_in"] = timestamp
            user_record["check_out"] = None
            user_record["break_start"] = None
            user_record["total_break_time"] = 0
            local_time = utc_to_local(timestamp)
            check_in_date = local_time.strftime('%Y-%m-%d')  # Get the check-in date
            check_in_time = local_time.strftime('%H:%M:%S')  # Get the check-in time
            # await channel.send(f"{user.mention} checked in at {check_in_time} on {check_in_date}.")

            # Record the check-in in the DataFrame (first check-in)
            attendance_df.loc[len(attendance_df)] = [user.name, check_in_date, check_in_time, None, None, "00:00:00",
                                                     None, 0]
            save_attendance_data()

    elif matched_command == "check out":
        # Handle check-out command
        if not user_record["check_in"]:
            await channel.send(f"{user.mention}, you haven't checked in yet!")
        elif user_record["check_out"]:
            await channel.send(
                f"{user.mention}, you have already checked out. Please check in again before checking out!")
        elif user_record["break_start"]:  # Ensure user has broken out before checking out
            await channel.send(f"{user.mention}, you cannot check out before ending your break!")
        else:
            # Calculate the total shift duration
            shift_duration_seconds = calculate_time_difference(user_record["check_in"], timestamp)
            total_break_time_seconds = user_record["total_break_time"]  # Total break time in seconds
            # Calculate total time worked by subtracting break time
            total_worked_seconds = max(shift_duration_seconds - total_break_time_seconds, 0)
            total_time_worked = seconds_to_hms(total_worked_seconds)  # Convert to hh:mm:ss format

            local_time = utc_to_local(timestamp)
            check_out_time = local_time.strftime('%H:%M:%S')  # Get the check-out time
            check_out_date = local_time.strftime('%Y-%m-%d')  # Get the check-out date
            # await channel.send(f"{user.mention} checked out at {check_out_time}. Shift completed!")

            # Update the check-out in the DataFrame
            idx = attendance_df[attendance_df["Employee Name"] == user.name].last_valid_index()
            attendance_df.at[idx, "Check-Out Date"] = check_out_date
            attendance_df.at[idx, "Check-Out Time"] = check_out_time
            attendance_df.at[idx, "Total Break Time (hh:mm:ss)"] = seconds_to_hms(user_record["total_break_time"])
            attendance_df.at[idx, "Total Time Worked (hh:mm:ss)"] = total_time_worked
            user_record["check_out"] = timestamp  # Mark that the user has checked out
            save_attendance_data()

    elif matched_command == "break in":
        # Handle break-in command
        if user_record["check_in"] is None:
            await channel.send(f"{user.mention}, you must check in before taking a break!")
        elif user_record["check_out"] is not None:  # No break-in after check-out without check-in again
            await channel.send(f"{user.mention}, you cannot break in after checking out! Please check in again.")
        elif user_record["break_start"]:
            await channel.send(f"{user.mention}, you are already on a break!")
        else:
            user_record["break_start"] = timestamp
            user_record["total_break_ins"] += 1  # Increment break-in count
            local_time = utc_to_local(timestamp)
            # await channel.send(f"{user.mention} started a break at {local_time.strftime('%I:%M %p')}. Break-in count: {user_record['total_break_ins']}")

    elif matched_command == "break out":
        # Handle break-out command
        if not user_record["break_start"]:
            await channel.send(f"{user.mention}, you are not on a break!")
        else:
            break_duration_minutes = calculate_time_difference(user_record["break_start"], timestamp, return_minutes=True)
            user_record["total_break_time"] += break_duration_minutes * 60  # Add break time in seconds
            user_record["break_start"] = None
            local_time = utc_to_local(timestamp)
            # await channel.send(f"{user.mention} ended a break at {local_time.strftime('%I:%M %p')}. Break duration: {break_duration_minutes:.0f} minutes.")

            # Update the break time in the DataFrame (convert seconds to hh:mm:ss format)
            idx = attendance_df[attendance_df["Employee Name"] == user.name].last_valid_index()
            attendance_df.at[idx, "Total Break Time (hh:mm:ss)"] = seconds_to_hms(user_record["total_break_time"])
            attendance_df.at[idx, "Total Break-Ins"] = user_record["total_break_ins"]
            save_attendance_data()


    else:
        await channel.send(f"{user.mention}, I didn't understand that. Please check your spelling and try again.")

    await bot.process_commands(message)  # Ensure commands still work


# Run the bot
bot.run("MTMyMjU5MzY1MzkxNDM0MTQzOA.G2-vPe.qB-0XezIL7amM5RviqMIUZqVemj9UmzSAvkYkg")
