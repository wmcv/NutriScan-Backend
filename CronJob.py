import random
import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_API_KEY)

challenge_ids = [
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222',
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',
    '55555555-5555-5555-5555-555555555555'
]

CHALLENGES_JSON_PATH = './weekly_challenges.json'

def load_challenges_from_json():
    try:
        with open(CHALLENGES_JSON_PATH, 'r') as file:
            challenges = json.load(file).get("challenges", [])
        return challenges
    except Exception as e:
        print(f"Error loading challenges from JSON: {e}")
        return []

def get_random_challenges():
    challenges = load_challenges_from_json()
    if challenges:
        return random.sample(challenges, 5)
    return []

def reset_challenge_progress():
    try:
        # Fetch all rows from the WeeklyChallengesUsers table
        response = supabase.table('WeeklyChallengesUsers').select('*').execute()
        if response:
            for user in response.data:
                user_id = user['user_id']
                # Update the challenge progress columns to 0 while keeping 'completed' unchanged
                update_response = supabase.table('WeeklyChallengesUsers').update({
                    'challenge1': 0,
                    'challenge2': 0,
                    'challenge3': 0,
                    'challenge4': 0,
                    'challenge5': 0
                }).eq('user_id', user_id).execute()
                if update_response:
                    print(f"Reset challenge progress for user {user_id}")
                else:
                    print(f"Error resetting progress for user {user_id}: {update_response['error']}")
        else:
            print("Failed to retrieve users from WeeklyChallengesUsers.")

    except Exception as e:
        print(f"Error resetting challenge progress: {e}")

def update_weekly_challenges():
    reset_challenge_progress()
    selected_challenges = get_random_challenges()
    if not selected_challenges:
        print("No challenges found to update.")
        return

    print(f"Updating weekly challenges at {datetime.now()}")
    print(f"Selected Challenges: {selected_challenges}")

    try:
        for i, challenge in enumerate(selected_challenges):
            challenge_id = challenge_ids[i]

            print('deleting')
            response = supabase.table('WeeklyChallenges').delete().eq('challenge', challenge_id).execute()
            print(response)

            print(f"Updating Challenge {challenge['name']} with ID {challenge_id}")
            response = supabase.table('WeeklyChallenges').insert({
                'id': i,
                'name': challenge['name'],
                'criteria': challenge['criteria'],
                'value': challenge['value'],
                'challenge': challenge_id
            }).execute()

            if 'data' in response:
                print(f"Challenge {challenge['name']} added successfully.")
            elif 'error' in response:
                print(f"Failed to insert challenge {challenge['name']}: {response['error']}")
            else:
                print(f"Unexpected response for challenge {challenge['name']}: {response}")
    except Exception as e:
        print(f"Error updating challenges in Supabase: {e}")


scheduler = BackgroundScheduler()
scheduler.add_job(update_weekly_challenges, 'cron', day_of_week='sun', hour=0, minute=0)
scheduler.start()

try:
    while True:
        pass
except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()
