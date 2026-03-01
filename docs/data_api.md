Aviasales Data API
Aviasales Data API — the way to get travel insights for your site or blog. Get flight price trends and find popular destinations for your customers.

Overview
Data is transferred from the cache based on the user's search history from Aviasales websites. The data is stored for 7 days for all types of queries. So it is recommended that you use them to generate static pages.

The data API access provides prices from the cache based on the user's search history.

For developers, documentation is available with examples of requests and answers in various programming languages, as well as a link to Postman.

Please note, that API methods use limits, which are described in the article API rate limits.

This documentation is for the public Aviasales API of the same name.

Access the API
To access the API, you must pass your token in the X-Access-Token header or in the token parameter.

You can find the API token in your Profile in the API token section.


Date format and response content
Dates are accepted in the formats YYYY-MM and YYYY-MM-DD.

The server response is always sent in JSON format with the following structure:

success — true for a successful request, false in case of errors
data — a result of the request; in case of an error will be empty: "data":{}
error — short description of the error that prevented request completion; for a successful request is equal to null
Dates and times are given in UTC, and formatted according to ISO 8601. Prices are given in rubles as of when the ticket is put in the search results. It is not recommended that you use expired prices (the approximate expiration date is given in the value of the expires_at parameter).

Important. We strongly recommend receiving data in compressed GZIP format, which saves a significant amount of time in receiving the response. To get data in compressed format, send the header Accept-Encoding: gzip, deflate.

To obtain access to the API to search for plane tickets and hotels, send a request.

Data by country (markets)
The API uses such a thing as a market. It depends on various factors, most often it is the language of the Aviasales website where users search for tickets.

Each search is associated with a specific market. This means that if a user searches for something on the aviasales.ru site, then the data in the cache will be only for the ru market and there will be no data for the us market (which, for example, aviasales.com is associated with).

By default, the market is determined by the place of departure (the origin parameter in the API request). If it is not possible to determine the market, then the data for the ru-market will be returned.

In all requests, you can use the market parameter to specify the market you need (for different markets, different agencies can be connected, which means that it is better for partners in America to see the cache for the US market, and not for the RU market).

You can see a list of available markets here.

Flight tickets for specific dates
Returns the cheapest tickets for specific dates found by Aviasales users in the last 48 hours. It is recommended to use instead of methods:

/v1/city-directions
/v1/prices/cheap
/v1/prices/direct
/v2/prices/latest
Request

https://api.travelpayouts.com/aviasales/v3/prices_for_dates?origin=MAD&destination=BCN&departure_at=2023-07&return_at=2023-08&unique=false&sorting=price&direct=false&cy=usd&limit=30&page=1&one_way=true&token=PutYourTokenHere

Request parameters

currency — the currency of prices. The default value is RUB
origin — An IATA code of a city or an airport of the origin
destination — An IATA code of a city or an airport of the destination (if you don't specify the origin parameter, you must set the destination)
departure_at — the departure date (YYYY-MM or YYYY-MM-DD)
return_at — the return date. For one-way tickets do not specify it
one_way —one-way tickets, possible values: true or false. true is used by default.
Since the query uses date grouping, only 1 one-way ticket is returned when true. To get more offers for round-trip tickets, use one_way=false.
direct — non-stop tickets, possible values: true or false. By default:  false
market — sets the market of the data source (by default, ru)
limit — the total number of records on a page. The default value — 30. The maximum value — 1000
page — a page number, is used to get a limited amount of results. For example, if we want to get the entries from 100 to 150, we need to set page=3, and limit=50
sorting — the assorting of prices:
price — by the price (the default value). For the directions, only city — city assorting by the price is possible
route — by the popularity of a route.
unique — returning only unique routes, if only origin specified, true or false. By default: false
token — your API token.
Response example

"success": true,
"data": [
{
"origin": «MAD",
"destination": "BCN",
"origin_airport": «MAD",
"destination_airport": "BCN",
"price": 5929,
"airline": "IB",
"flight_number": «3002",
"departure_at": "2023-07-28T07:00:00+02:00",
"return_at": "2023-08-26T14:30:00+02:00",
"transfers": 0,
"return_transfers": 0,
"duration": 165,
"duration_to": 80,
"duration_back": 85,
"link": "/search/MAD2807BCN26081?t=IB16905204001690525200000080MADBCN16930530001693058100000085BCNMAD_29ee244e5b536fb9099d8ec2ca842b19_78\u0026search_date=11052023\u0026expected_price_uuid=7531ddb1-26b4-4df9-891e-81dc54d48b2a\u0026expected_price_currency=usd»"
}
Response data

origin — the point of departure
destination — the point of destination
origin_airport — the IATA of the origin airport
destination_airport — the IATA of the destination airport
price — price of the ticket
airline — the IATA of the airline
flight_number — flight number
departure_at — departure date
return_at — return date
transfers — number of stops on the way to the destination
return_transfers — number of stops on the way back
duration — total round trip duration in minutes
duration_to — duration of the flight to the destination in minutes
duration_back — duration of the return flight in minutes
link — the ticket link. Add the code to the URL https://www.aviasales.com/ to open the search results on the given route on Aviasales. Use our deep link creation form to create your partner link out of the resulting link
currency — the currency of prices.
How you can replace the outdated methods with this endpoint:
/v1/prices/cheap — set direct=false; sorting=price
/v1/prices/direct — set direct=true; sorting=price
/v1/city-directions — set sorting=route;unique=true. Pass only the origin parameter.
Prices for airline tickets for a period of time
Returns the prices of the airline tickets for a specific period of time.

Request

http://api.travelpayouts.com/aviasales/v3/get_latest_prices

Request parameters

currency — the currency of prices.
origin — IATA code of a city or an airport of the departure.
destination — IATA code of a city or an airport of the destination (if you don't specify the origin parameter, you must set the destination parameter)
beginning_of_period — the beginning of the period, within which the dates of departure fall. Must be specified if period_type is equal to a month.
period_type — the period for which the tickets have been found. Allowed values include:
year — tickets found in the specified year. In beginning_of_period the year is specified in YYYY format.
month — tickets found for the specified in the beginning_of_period month (use YYYY-MM-DD format).
day — tickets found for the specified in the beginning_of_period day (use YYYY-MM-DD format).
If no period_type is specified, tickets for flights in the current month are displayed.

group_by — the rule for grouping:
dates — by dates (default value).
directions — by destinations.
one_way — true - one way, false - back-to-back. Default value— true.
page — a page of the result, it's used for chunked reading of a large result. Default value — 1.
market — sets the market of the data source.
sorting — the rule for the sorting of prices:
price — by the price (default value). For the directions from city to city only sorting by the price is possible.
route — by the popularity of the route.
distance_unit_price — by the price for 1 km.
trip_duration — the duration of stay in the destination place in days.
trip_class — the flight class:
0 — the economy class
1 — the business class
2 — the first class
Request example

http://api.travelpayouts.com/aviasales/v3/get_latest_prices?currency=rub&period_type=year&page=1&show_to_affiliates=true&sorting=price&token=PutYourTokenHere

Response example

{
   "success":true,
   "data":[{
      "show_to_affiliates":true,
      "origin":"WMI",
      "destination":"WRO",
      "depart_date":"2021-12-07",
      "return_date":"2021-12-13",
      "number_of_changes":0,
      "value":1183,
      "found_at":"2021-09-22T14:08:45+04:00",
      "distance":-1,
      "actual":true
   }]
}
Response data

success — the result of the request.
data:
origin — IATA code of a city of the departure
destination — IATA code of a city of the destination
depart_date — the date of the departure
distance — the flight distance in kilometers
duration — the flight duration in minutes
return_date — the date of the return flight
number_of_changes — number of transfers
value — ticket price
found_at — the time and the date, for which a ticket was found
trip_class — the flight class:
0 — the economy class
1 — the business class
2 — the first class
The calendar of prices for a month
Brings back the prices for each day of the month, grouped together by the number of transfers.

Request

http://api.travelpayouts.com/v2/prices/month-matrix?currency=usd&origin=BCN&destination=HKT&show_to_affiliates=true&token=PutHereYourToken

Request parameters

currency — the airline ticket’s The default value — RUB
origin — the point of departure. The IATA city code or the country code. The length — from 2 to 3 symbols
destination — the point of destination. The IATA city code or the country code. The length — from 2 to 3 symbols
month — the beginning of the month in the YYYY-MM-DD format
show_to_affiliates — false — all the prices, true — just the prices, found using the partner marker (recommended). The default value — true
market — sets the market of the data source (by default, ru)
token — the individual affiliate token
trip_duration — the length of stay in weeks. If not specified, the result will be tickets to one-way
one_way — false — returns roundtrip tickets, true — just the one way tickets. The default value — true.
limit — an optional parameter that specifies the number of days in a month. By default, its value is 30, but for months with 31 days, you need to set limit=31 in the request.
Response example

{{
   "success":true,
   "data":[{
      "show_to_affiliates":true,
      "trip_class":0,
      "origin":"BCN",
      "destination":"HKT",
      "depart_date":"2021-10-01",
      "return_date":"",
      "number_of_changes":1,
      "value":29127,
      "found_at":"2021-09-24T00:06:12+04:00",
      "distance":8015,
      "actual":true
   }]
}
Response data

origin — the point of departure
destination — the point of destination
show_to_affiliates — false — all the prices, true — just the prices, found using the partner marker (recommended). The default value — true
trip_class — the flight class:
0 — Economy class
1 — Business class
2 — First
depart_date — the date of departure
return_date — the date of return
number_of_changes — the number of transfers
value — the cost of a flight, in the currency specified
found_at — the time and the date at/on which a ticket was found
distance — the distance between the point of departure and the point of destination
actual — the actuality of an offer
The prices for the alternative directions
Returns prices for the directions that include tickets between cities closest to a given origin and destination.

Request

https://api.travelpayouts.com/v2/prices/nearest-places-matrix?currency=usd&origin=BCN&destination=HKT&show_to_affiliates=true&distance=1000&limit=5&token=PutHereYourToken

Request parameters

currency — the airline ticket’s The default value — RUB
origin — the point of departure. The IATA city code or the country code. The length — from 2 to 3 symbols
destination — the point of destination. The IATA city code or the country code. The length — from 2 to 3 symbols
limit — the number of variants entered, from 1 to 20, where 1 is just the variant with the specified points of departure and the points of destination
show_to_affiliates — false — all the prices, true — just the prices, found using the partner marker (recommended). The default value — true
market — sets the market of the data source (by default, ru)
depart_date (optional) — month of departure (yyyy-mm)
return_date (optional) — month of return (yyyy-mm)
flexibility — expansion of the range of dates upward or downward. The value may vary from 0 to 7, where 0 shall show the variants for the dates specified and 7 shall show all the variants found for a week prior to the specified dates and a week after
distance — the number of variants entered, from 1 to 20, where 1 is just the variant with the specified points of departure and the points of destination
token — individual affiliate token
Response example

{
  "prices":[
  {
    "value":26000.0,
    "trip_class":0,
    "show_to_affiliates":true,
    "return_date":"2021-09-18",
    "origin":"BAX",
    "number_of_changes":0,
    "gate":"AMADEUS",
    "found_at":"2021-07-28T04:57:47Z",
    "duration":null,
    "distance":3643,
    "destination":"SIP",
    "depart_date":"2021-09-09",
    "actual":true
  }
  ],
  "origins":[
    "BAX"
  ],
  "errors":{
    "amadeus":{
  }
 },
  "destinations":[
    "SIP"
  ]
 }
Response data

origin — the point of departure
destination — the point of destination
show_to_affiliates — false — all the prices, true — just the prices, found using the partner marker (recommended). The default value — true
trip_class — the flight class:
0 — Economy class
1 — Business class
2 — First
depart_date — the date of departure
return_date — the date of return
number_of_changes — the number of transfers
value — the cost of a flight, in the currency specified
found_at — the time and the date at/on which a ticket was found
distance — the distance between the point of departure and the point of destination.
actual — the actuality of an offer
duration — the flight duration in minutes, taking into account direct and expectations
errors — if the error «Some error occurred» is returned, this area does not have the data in the cache
gate — the agents, which was found on the ticket
token — the individual affiliate token
The calendar of prices for a week
Returns airfare prices for a 7-day period around the specified departure and return dates provided in the request.

Based on the depart_date and return_date parameters, the method automatically creates date ranges: from 3 days before to 4 days after the selected date — both for departure and return. This allows you to get prices for a 7-day period around each specified date.

For example, if you set depart_date = 2025-05-03, you will receive ticket prices for departures between 2025-05-01 and 2025-05-07.

Request

http://api.travelpayouts.com/v2/prices/week-matrix?currency=usd&origin=BCN&destination=HKT&show_to_affiliates=true&depart_date=2021-09-04&return_date=2021-09-18&token=PutHereYourToken

Request parameters

currency — the airline ticket’s The default value — RUB
origin — the point of departure. The IATA city code or the country code. The length — from 2 to 3 symbols
destination — the point of destination. The IATA city code or the country code. The length — from 2 to 3 symbols
show_to_affiliates — false — all the prices, true — just the prices, found using the partner marker (recommended). The default value — true
depart_date (optional) — day or month of departure (yyyy-mm-dd or yyyy-mm)
return_date (optional) — day or month of return (yyyy-mm-dd or yyyy-mm)
market — sets the market of the data source (by default, ru)
token — individual affiliate token
Response example

{
  success:true,
  data:[
  {
    show_to_affiliates:true,
    trip_class:0,
    origin:BCN,
    destination:HKT,
    depart_date:2021-03-01,
    return_date:2021-03-15,
    number_of_changes:1,
    value:71725,
    found_at:2021-02-19T00:04:37+04:00,
    distance:8015,
    actual:true
  }]
}
Response data

origin — the point of departure
destination — the point of destination
show_to_affiliates — false — all the prices, true — just the prices, found using the partner marker (recommended). The default value — true
trip_class — the flight class (0 — Economy class)
depart_date — the date of departure
return_date — the date of return
number_of_changes — the number of transfers
value — the cost of a flight, in the currency specified
found_at — the time and the date at/on which a ticket was found
distance — the distance between the point of departure and the point of destination
actual — the actuality of an offer
Cheapest tickets
Returns the cheapest non-stop tickets, as well as tickets with 1 or 2 stops, for the selected route with departure/return date filters.

Request

http://api.travelpayouts.com/v1/prices/cheap?origin=LON&destination=HKT&depart_date=2022-11&return_date=2022-12&token=PutHereYourToken

Important: Old dates may be specified in a query. No error will be generated, but no data will be returned.

Request parameters

origin — IATA code of the departure city. IATA code is shown by uppercase letters, for example, LON
destination — IATA code of the destination city (for all routes send the empty field). IATA code is shown by uppercase letters, for example, LON
depart_date (optional) — month of departure (yyyy-mm)
return_date (optional) — month of return (yyyy-mm)
page — optional parameter, is used to display the found data (by default the page displays 100 found prices. If the destination isn’t selected, there can be more data. In this case, use the page, to display the next set of data, for example, page=2)
market — sets the market of the data source (by default, ru)
token — individual affiliate token
currency — the currency of prices. The default value is RUB
Response example

{
   "success": true,
   "data": {
      "HKT": {
         "0": {
            "price": 35443,
            "airline": "UN",
            "flight_number": 571,
            "departure_at": "2021-06-09T21:20:00Z",
            "return_at": "2021-07-15T12:40:00Z",
            "expires_at": "2021-01-08T18:30:40Z"
         },
         "1": {
            "price": 27506,
            "airline": "CX",
            "flight_number": 204,
            "departure_at": "2021-06-05T16:40:00Z",
            "return_at": "2021-06-22T12:00:00Z",
            "expires_at": "2021-01-08T18:38:45Z"
         },
         "2": {
            "price": 31914,
            "airline": "AB",
            "flight_number": 8113,
            "departure_at": "2021-06-12T13:45:00Z",
            "return_at": "2021-06-24T20:30:00Z",
            "expires_at": "2021-01-08T15:17:42Z"
         }
      }
   }
}
Response data

0, 1, 2 — sequence number in the search results
price — ticket price (in the currency specified in the currency parameter)
airline — IATA code of the airline operating the flight
flight_number — flight number
departure_at — departure Date
return_at — return Date
expires_at — date on which the found price expires (UTC+0)
token — individual affiliate token
Cheapest tickets grouped by the specific attribute
Returns the cheapest tickets grouped by the specific attribute found by Aviasales users in the last 48 hours. It is recommended to use instead of methods:

/v1/prices/calendar
/v1/prices/monthly
Request

https://api.travelpayouts.com/aviasales/v3/grouped_prices

Request parameters

currency — the currency of prices. The default value is RUB
origin — An IATA code of a city or an airport of the origin
destination — An IATA code of a city or an airport of the destination
group_by — grouping parameter:
departure_at — by the departure date (the default value)
month — by month.
departure_at — the departure date (YYYY-MM or YYYY-MM-DD)
market — sets the market of the data source (by default, ru)
return_at — the return date. For one-way tickets do not specify it
direct — non-stop tickets, true or false. By default: false
min_trip_duration — minimum length of trip in days (difference between departure and return date).
max_trip_duration — maximum length of trip in days (difference between departure and return date).
Response example

{
"success":true,
"data":{
"2022-02-01":{
"origin":"LON",
"destination":"BCN",
"origin_airport":"VKO",
"destination_airport":"BCN",
"price":3390,
"airline":"UT",
"flight_number":"381",
"departure_at":"2022-02-01T01:00:00+03:00",
"return_at":"2022-02-03T06:25:00+03:00",
"transfers":0,
"return_transfers":0,
"duration":175,
"link":"/search/LON0102BCN03022?t=UT16436664001643671800000090VKOBCN16438587001643863800000085BCNVKO_3a03a03671180cb6d4ddc75e3aaf8e0b_6780&search_date=28122021&expected_price_uuid=b2dcc898-1ba8-4d86-8f9e-b9c0c9bb10c7&expected_price_currency=rub"
}
}
}
Response data

origin — the point of departure
destination — the point of destination
origin_airport — the IATA of the origin airport
destination_airport — the IATA of the destination airport
price — the price of the ticket
airline — the IATA of the airline
flight_number — flight number
departure_at — departure date
return_at — return date
transfers — number of stops on the way to the destination
return_transfers — number of stops on the way back
duration — the flight duration in minutes
link — the ticket link. Add the code to the URL https://www.aviasales.com/search/ to open the search results on the given route on Aviasales. Use our deep link creation form to create your partner link out of the resulting link
currency — the currency of prices.
How you can replace the outdated methods with this endpoint:
/v1/prices/calendar — pass departure_at or return_at in group_by
/v1/prices/monthly — pass month in group_by, do not specify departure_at and return_at.
Non-stop tickets
Returns the cheapest non-stop ticket for the selected route with departure/return date filters.

Request

http://api.travelpayouts.com/v1/prices/direct?origin=LON&destination=BCN&depart_date=2022-11&return_date=2022-12&token=PutHereYourToken

Request parameters

origin — IATA code of the departure city. The IATA code is shown in uppercase letters
destination — IATA code of the destination city (for all routes, enter -). The IATA code is shown in uppercase letters
market — sets the market of the data source (by default, ru)
depart_date (optional) — a month of departure (yyyy-mm)
return_date (optional) — a month of return (yyyy-mm)
token — individual affiliate token
currency — the currency of prices. The default value is RUB
Response example

{
   "success": true,
   "data": {
      "BCN": {
         "0": {
            "price": 4363,
            "airline": "UT",
            "flight_number": 369,
            "departure_at": "2021-06-27T11:35:00Z",
            "return_at": "2021-07-04T16:00:00Z",
            "expires_at": "2021-01-08T20:21:46Z"
         }
      }
   }
}
Response data

price — ticket price (in specified currency)
airline — IATA code of airline operating the flight
flight_number — flight
departure_at — departure date
return_at — return date
expires_at — date on which the found price expires (UTC+0)
Flight price trends
Returns the cheapest non-stop, one-stop, and two-stop flights for the selected route for each day of the selected month.

Important: this method has a limit of 10 requests per second.

Request

http://api.travelpayouts.com/v1/prices/calendar?depart_date=2022-11&origin=LON&destination=BCN&calendar_type=departure_date&token=PutHereYourToken

Request parameters

origin — IATA code of the departure city. The IATA code is shown in uppercase letters
destination — IATA code of the destination city. The IATA code is shown in uppercase letters
departure_date (optional) — a month of departure (yyyy-mm)
return_date (optional) — a month of return (yyyy-mm).
calendar_type — field used to build the calendar. Equal to either: departure_date or return_date
length (optional) — a length of stay in the destination city
market — sets the market of the data source (by default, ru)
token — individual affiliate token
currency — the currency of prices. The default value is RUB
Response example

{
   "success": true,
   "data": {
      "2021-06-01": {
         "origin": "LON",
         "destination": "BCN",
         "price": 12449,
         "transfers": 1,
         "airline": "PS",
         "flight_number": 576,
         "departure_at": "2021-06-01T06:35:00Z",
         "return_at": "2021-07-01T13:30:00Z",
         "expires_at": "2021-01-07T12:34:14Z"
      },
      "2021-06-02": {
         "origin": "LON",
         "destination": "BCN",
         "price": 13025,
         "transfers": 1,
         "airline": "PS",
         "flight_number": 578,
         "departure_at": "2021-06-02T17:00:00Z",
         "return_at": "2021-06-11T13:30:00Z",
         "expires_at": "2021-01-06T17:15:47Z"
      },
      ...
     "2021-06-30": {
         "origin": "LON",
         "destination": "BCN",
         "price": 13025,
         "transfers": 1,
         "airline": "PS",
         "flight_number": 578,
         "departure_at": "2021-06-30T17:00:00Z",
         "return_at": "2021-07-23T13:30:00Z",
         "expires_at": "2021-01-07T20:15:34Z"
      }
   }
}
Response data

origin — IATA code of the departure city
destination — IATA code of the destination city
price — ticket price in the specified currency
transfers — number of stops
airline — IATA code of airline
flight_number — flight number
departure_at — departure date
return_at — return date
expires_at — when the found price expires (UTC+0)
Popular airline routes
This API method has been deprecated since March 14, 2022. Feel free to use the method named prices_for_dates.
Description

Returns routes for which an airline operates flights, sorted by popularity.

Request

http://api.travelpayouts.com/v1/airline-directions?airline_code=SU&limit=10&token=PutHereYourToken

Request parameters

airline_code — IATA code of an airline
limit — records limit per page. The default value is 100. Not less than 1000
token — individual affiliate token
Response example

{
   "success": true,
   "data": {
      "LON-BKK": 187491,
      "LON-BCN": 113764,
      "LON-PAR": 91889,
      "LON-NYC": 77417,
      "LON-PRG": 71449,
      "LON-ROM": 67190,
      "LON-TLV": 62132,
      "LON-HKT": 58549,
      "LON-GOI": 47341,
      "LON-IST": 45553
   },
   "error": null,
   "currency":"rub"
}
Description of response

Returns a list of popular routes of an airline, sorted by popularity.

The popular destinations
Brings back the most popular directions from a specified city.

Request

http://api.travelpayouts.com/v1/city-directions?origin=LON&currency=usd&token=PutHereYourToken

Request parameters

currency — the airline ticket’s The default value — RUB
origin — the point of departure. The IATA city code or the country code. The length — from 2 to 3 symbols
token — the individual affiliate token
Response example

{
  "success":true,
  "data":{
    "AER":{
      "origin":"LON",
      "destination":"AER",
      "price":3673,
      "transfers":0,
      "airline":"WZ",
      "flight_number":125,
      "departure_at":"2021-03-08T16:35:00Z",
      "return_at":"2021-03-17T16:05:00Z",
      "expires_at":"2021-02-22T09:32:44Z"
    }
  },
  "error":null,
  "currency":"rub"
}
Response data

origin — the point of departure
destination — the point of destination
departure_at — the date of departure
return_at — the date of return
expires_at — the date on which the found price expires (UTC+0)
number_of_changes — the number of transfers
price — the cost of a flight, in the currency specified
found_at — the time and the date at/on which a ticket was found
transfers — the number of direct
airline — the IATA of the airline
flight_number— the flight number
currency — the currency of response
Cheapest tickets to popular destinations
Returns the cheapest tickets to popular destinations. Popular destinations are generated based on data about searches and ticket bookings to the specified destination by other users. The API analyzes statistics and returns a list of departure points from which tickets to this destination are most frequently searched.

Request
http://api.travelpayouts.com/aviasales/v3/get_popular_directions

Request parameters
destination — IATA code of the destination city. The code must be in uppercase, for example, JFK.
locale — the language of the returned results.
currency — currency in which ticket prices are displayed.
limit — number of results to display, ranging from 1 to 30.
page — a page number, is used to get a limited amount of results. The response will return tickets within the range: [(page — 1) * limit; page * limit]. For example, to get tickets 60 to 90, set page=3 and limit=30.
token — Your personal API token.
Request example
http://api.travelpayouts.com/aviasales/v3/get_popular_directions?destination=MOW&locale=ru&currency=RUB&limit=20&page=1&token=РазместитеЗдесьВашТокен

Response example
{
  "currency": "eur",
  "data": {
    "destination": {
      "city_name": "Paris",
      "country_name": "France",
      "declension": ""
    },
    "origin": [
      {
        "city_name": "New York City",
        "city_iata": "JFK",
        "departure_at": "2025-01-15",
        "return_at": "",
        "price": 1681,
        "declensions": {}
      }
    ]
  },
  "success": true
}
Response parameters
success — the status of the request.
currency — currency in which ticket prices are displayed.
data — retrieved data:
destination — information about the destination city:
city_name — the name of the destination city
country_name — the name of the destination country
declensions — declensions of the city name, if available
origin — information about the departure city:
city_name — the name of the departure city
city_iata — IATA code of the departure city
departure_at — departure date in the format YYYY-MM-DD
return_at — return date
price — ticket price in the specified currency
declensions — declensions of the city name, if available
Flights special offers
Returns abnormally low prices for air tickets to selected destinations.

Request
https://api.travelpayouts.com/aviasales/v3/get_special_offers

Request parameters
origin — an IATA code of a city or an airport of the origin
Note: If you don't specify the origin, it will be automatically determined by the IP address.
destination — an IATA code of a city or an airport of the destination
locale — language on which the result will be returned
currency — currency in which prices were given
market — sets the market of the data source (by default, ru)
airline — an airline IATA code
token — individual affiliate token.
Request example
https://api.travelpayouts.com/aviasales/v3/get_special_offers?origin=LON&destination=BCN&airline=s7&locale=en&token=PlaceYourTokenHere

Response

{
  "currency": "rub",
  "data": [
    {
      "airline": "N4",
      "airline_title": "Nordwind Airlines",
      "color": "CD202C",
      "departure_at": "2021-09-14T08:55:00+03:00",
      "destination": "BCN",
      "destination_airport": "BCN",
      "destination_name": "Saint Petersburg",
      "duration": 85,
      "flight_number": "177",
      "link": "/LON1409BCN1?t=N416315989001631604000000000SVOBCN_3d507ff71944b34ca6e5016e0c0fce85_1413\u0026search_date=29072021\u0026expected_price_uuid=9a904680-6d3b-4dee-a361-b85da4e63590\u0026expected_price_currency=rub",
      "mini_title": "Flight deals from Moscow",
      "origin": "LON",
      "origin_airport": "SVO",
      "origin_name": "Moscow",
      "price": 1413,
      "search_id": "9a904680-6d3b-4dee-a361-b85da4e63590",
      "signature": "3d507ff71944b34ca6e5016e0c0fce85",
      "title": "Flight deals from Moscow to Saint Petersburg"
    }
  ],
  "success": true
}
Response data
airline — the code of an airline
airline_title — the name of an airline
destination — an IATA code of a city of the destination
destination_airport — an IATA code of an airport of the destination
flight_number — the number of a flight
signature — the ticket ID (used for building of the deep link)
duration — flight duration in minutes
origin_airport — an IATA code of an airport of the origin
price — a ticket price
return_at — a date of return departure (RFC3339 format)
search_id — the search ID (used for creating a deep link)
departure_at — a date of departure (RFC3339 format)
mini_title — a short title for a special offer
origin — an IATA code of a city of the origin
color — airline's brand color (present as a RGB code)
link — a link to the flight ticket.
Add this code to the address https://www.aviasales.ru/search/ to open search results for this destination on the Aviasales website (please note, if tickets are sold out, the link will redirect to a new search).Use our deep link creation form to create your partner link out of the resulting link.
title — a title for a special offer
Search flight tickets by price
The endpoint returns flight tickets with specific prices.

Request
https://api.travelpayouts.com/aviasales/v3/search_by_price_range?origin=LON&destination=BCN&value_min=100&value_max=500&one_way=true&direct=false&locale=en&currency=usd&market=us&limit=30&page=1&token=PutHereYourToken

Request parameters
origin — IATA code of the departure city. The IATA code is shown in uppercase letters
destination — IATA code of the destination city (for all routes, enter -). The IATA code is shown in uppercase letters
value_min — minimum price of the ticket
value_max — maximum price of the ticket
one_way — one-way tickets, possible values: true or false, where true - one way, false - back-to-back
direct — non-stop tickets, possible values: true or false. By default: false.
locale — the language of the returned results
currency — currency in which ticket prices are given
market — sets the market of the data source
limit — the total number of records on a page
page — a page number, is used to get a limited amount of results.the currency of prices
token — your API token
Response example
{
  "currency": "eur",
  "data": [
    {
      "departure_at": "2024-11-03",
      "destination_airport": "BCN",
      "destination_code": "BCN",
      "destination_name": "Barcelona",
      "duration": 90,
      "link": "/BCN0311LON1?t=DP16359621001635967500000000LHRBCN_2560c41c52a83fba3afad4d8770d1ee9_6088\u0026search_date=28052024\u0026expected_price_uuid=0cd8aa16-9169-4099-9076-574fbee7da8a\u0026expected_price_currency=rub",
      "origin_airport": "LHR",
      "origin_code": "LON",
      "origin_name": "London",
      "price": 588,
      "transfers": 0
    }
  ],
  "success": true
}
Response data
currency — the currency of prices
departure_at — the date of the departure
destination_airport — the IATA of the destination airport
destination_code — the IATA of the destination city
destination_name — name of the destination city
duration — the flight duration in minutes
link — a link to the flight ticket
Add this code to the address https://www.aviasales.com/search/ to open search results for this destination on the Aviasales website (please note, if tickets are sold out, the link will redirect to a new search). Use our deep link creation form to create your partner link out of the resulting link.
origin_airport — the IATA of the departure airport
origin_code — the IATA of the departure city
origin_name — name of the departure city
price — the price of the ticket
transfers — number of stops on the way to the destination.
Logos of airlines
Flight logos are available here: http://pics.avs.io/width/height/iata.png

where, width — the width of the logo, height — the height of the logo, iata — IATA airline code. The size of the logo can be anything.

For example http://pics.avs.io/200/200/UN.png.

Reduction of prices into the other currency
Brings back the current rate of all popular currencies to RUB.

Request

http://yasen.aviasales.com/adaptors/currency.json

Response example

{
  "cny":8.24394,
  "eur":57.1578,
  "mzn":1.49643,
  "nio":1.97342,
  "usd":51.1388,
  "hrk":7.48953
}