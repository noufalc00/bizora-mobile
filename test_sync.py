from sync_service import sync_data

# Create a test dictionary
test_data = {"business_name": "Test Company", "address": "Test Address"}

# Try to send it to the 'companies' table
try:
    success = sync_data('companies', test_data)
    if success:
        print("SUCCESS: The bridge is working! Check your Supabase Dashboard.")
    else:
        print("FAILURE: The sync didn't work. Check your .env file.")
except Exception as e:
    print(f"ERROR: An unexpected error occurred: {e}")
