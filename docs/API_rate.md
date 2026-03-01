API rate limits
As of June 14, 2024, we have introduced new API rate limits.
The new limits are measured in the number of requests per minute, not 5 minutes and an hour as it was before. Detailed information can be found in the table below.
To ensure the stable work of Aviasales Data API and Travelpayouts statistics API, the number of requests to servers is limited. This allows us to avoid an increased workload from unscrupulous partners, which can result in lower API work speed for all partners.

We use the maximum number of requests per minute as the limit.

This allows us to:

adjust the peak load (for example, when a partner's website has many visitors at the same time, and requests to API are tied up in each click to the website);
optimize work with API in general (for example, use of cash by partners and distribution of requests to API evenly throughout the day).
The table provides limitations for all Aviasales and Travelpayouts API methods valid from 14.06.2024.

Method	Limitation of the Number of Requests Per Minute
/v1/prices/calendar	300
/v1/prices/cheap	300
/v1/prices/direct	180
/v1/prices/monthly	60
/v1/city-directions	600
/v2/prices/latest	300
/v2/prices/month-matrix	300
/v2/prices/nearest-places-matrix	60
/v2/prices/week-matrix	60
/v2/prices/special-offers	600
/data/something.json	600
/v3/get_latest_prices	300
/v3/prices_for_dates	600
/v3/grouped_prices	600
/v3/get_special_offers	600
/v3/get_popular_directions	600
/v3/search_by_price_range	600
/statistics/v1/execute_query*	30
/graphql/v1/	60
If the limitations are exceeded, the 429 error code will be sent in response to the request.

For example, if you use a method with a limit of 60 requests per minute, but you send 60 requests in the first 5 seconds, access to the API will be blocked for 55 seconds. You will receive an error with code 429 until the specified time passes, at which point the block will be removed and access to API will be automatically unblocked.

We strongly recommend that you use cached data to limit the number of requests to API. If you need to know the number of sent requests, make sure to do so independently on your end.

Here are a few tips on how to optimize API requests:

Do not send excessive requests.
Optimize your code to exclude API requests, the responses to which don’t contain any necessary data.
Cache frequently used data on the server or on the client by using DOM storage. You can also save the received information in the database or write it in a file.
If you have worked with API for a long time, switch to new methods (api/v3), which contain more data (so that you can send fewer requests).
If you have carried out the optimization, but the limitations are still being exceeded, feel free to contact our support team at support@travelpayouts.com.

How to Check Available Limits
When using the requests listed in the table above, the response includes headers with values that allow you to monitor the rate limits:

X-Rate-Limit — the total limit for this specific request.
X-Rate-Limit-Remaining — the number of remaining requests you can make within the current minute.
X-Rate-Limit-Reset — the time in seconds until the current limit resets and updates.
With this information, you can optimize your API usage and avoid exceeding the limits.