import geoip2.database

# This reader object should be reused across lookups as creation of it is
# expensive.
with geoip2.database.Reader('/path/to/maxmind-database.mmdb') as reader:
    response = reader.city('128.101.101.101')
    print(response.country.iso_code)