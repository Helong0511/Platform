import datetime

key = ''
startDate = datetime.datetime.now().strftime('%Y-%m-%d')
endDate = datetime.datetime.now().strftime('%Y-%m-%d')

url = f'https://macan-native.com/api/advertisers/reporting/entity?key={key}&startDate={startDate}&endDate={endDate}'



