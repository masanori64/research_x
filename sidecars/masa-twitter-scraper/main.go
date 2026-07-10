package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"net/http"
	"os"
	"reflect"
	"regexp"
	"strings"
	"time"
	"unsafe"

	twitterscraper "github.com/masa-finance/masa-twitter-scraper"
)

type outputTweet struct {
	ID        string                 `json:"id"`
	URL       string                 `json:"url,omitempty"`
	Text      string                 `json:"text,omitempty"`
	CreatedAt string                 `json:"created_at,omitempty"`
	User      map[string]string      `json:"user,omitempty"`
	Raw       map[string]interface{} `json:"raw,omitempty"`
}

func main() {
	kind := flag.String("kind", "profile", "target kind: profile, search, or url")
	target := flag.String("target", "", "screen name, query, tweet URL, or tweet id")
	limit := flag.Int("limit", 20, "maximum tweets to emit")
	cookiesFile := flag.String("cookies-file", "", "JSON file containing []*http.Cookie")
	format := flag.String("format", "jsonl", "output format, only jsonl is supported")
	flag.Parse()

	if *format != "jsonl" {
		exitErr(errors.New("only --format jsonl is supported"))
	}
	if strings.TrimSpace(*target) == "" {
		exitErr(errors.New("--target is required"))
	}
	if *limit < 1 {
		*limit = 1
	}

	scraper := twitterscraper.New()
	if *cookiesFile != "" {
		cookies, err := loadCookies(*cookiesFile)
		if err != nil {
			exitErr(err)
		}
		scraper.SetCookies(cookies)
		forceCookieSession(scraper)
	} else if err := scraper.LoginOpenAccount(); err != nil {
		exitErr(err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	switch *kind {
	case "profile":
		err := emitProfile(ctx, scraper, screenName(*target), *limit)
		exitErr(err)
	case "search":
		err := emitSearch(ctx, scraper, *target, *limit)
		exitErr(err)
	case "url":
		err := emitTweet(scraper, tweetID(*target))
		exitErr(err)
	default:
		exitErr(fmt.Errorf("unsupported --kind %q", *kind))
	}
}

func emitProfile(
	ctx context.Context,
	scraper *twitterscraper.Scraper,
	screenName string,
	limit int,
) error {
	count := 0
	for result := range scraper.GetTweets(ctx, screenName, limit) {
		if result.Error != nil {
			return result.Error
		}
		if err := writeTweet(result.Tweet); err != nil {
			return err
		}
		count++
		if count >= limit {
			return nil
		}
	}
	return nil
}

func emitSearch(
	ctx context.Context,
	scraper *twitterscraper.Scraper,
	query string,
	limit int,
) error {
	scraper.SetSearchMode(twitterscraper.SearchLatest)
	count := 0
	for result := range scraper.SearchTweets(ctx, query, limit) {
		if result.Error != nil {
			return result.Error
		}
		if err := writeTweet(result.Tweet); err != nil {
			return err
		}
		count++
		if count >= limit {
			return nil
		}
	}
	return nil
}

func emitTweet(scraper *twitterscraper.Scraper, id string) error {
	if id == "" {
		return errors.New("url target is not a tweet URL or tweet id")
	}
	tweet, err := scraper.GetTweet(id)
	if err != nil {
		return err
	}
	return writeTweet(*tweet)
}

func writeTweet(tweet twitterscraper.Tweet) error {
	row := outputTweet{
		ID:        tweet.ID,
		URL:       tweet.PermanentURL,
		Text:      tweet.Text,
		CreatedAt: tweet.TimeParsed.Format(time.RFC3339),
		User: map[string]string{
			"screen_name": tweet.Username,
			"name":        tweet.Name,
		},
		Raw: map[string]interface{}{
			"conversation_id": tweet.ConversationID,
			"html":            tweet.HTML,
			"likes":           tweet.Likes,
			"replies":         tweet.Replies,
			"retweets":        tweet.Retweets,
			"views":           tweet.Views,
		},
	}
	encoder := json.NewEncoder(os.Stdout)
	return encoder.Encode(row)
}

func loadCookies(path string) ([]*http.Cookie, error) {
	handle, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer handle.Close()

	var cookies []*http.Cookie
	if err := json.NewDecoder(handle).Decode(&cookies); err != nil {
		return nil, err
	}
	return withDomainVariants(cookies), nil
}

func withDomainVariants(cookies []*http.Cookie) []*http.Cookie {
	allowed := map[string]bool{
		"auth_token": true,
		"ct0":        true,
		"twid":       true,
		"kdt":        true,
		"lang":       true,
	}
	result := make([]*http.Cookie, 0, len(cookies)*3)
	for _, cookie := range cookies {
		if cookie == nil {
			continue
		}
		if !allowed[cookie.Name] {
			continue
		}
		for _, domain := range []string{cookie.Domain, ".x.com", ".twitter.com"} {
			if domain == "" {
				continue
			}
			clone := *cookie
			clone.Domain = domain
			clone.Value = strings.ReplaceAll(clone.Value, `"`, "")
			if clone.Path == "" {
				clone.Path = "/"
			}
			result = append(result, &clone)
		}
	}
	return result
}

func screenName(value string) string {
	value = strings.TrimSpace(value)
	value = strings.TrimPrefix(value, "@")
	re := regexp.MustCompile(`(?:x\.com|twitter\.com)/([^/?#]+)`)
	if match := re.FindStringSubmatch(value); len(match) == 2 {
		return match[1]
	}
	return value
}

func tweetID(value string) string {
	value = strings.TrimSpace(value)
	if regexp.MustCompile(`^\d+$`).MatchString(value) {
		return value
	}
	re := regexp.MustCompile(`/status(?:es)?/(\d+)`)
	if match := re.FindStringSubmatch(value); len(match) == 2 {
		return match[1]
	}
	return ""
}

func exitErr(err error) {
	if err == nil {
		return
	}
	fmt.Fprintln(os.Stderr, err.Error())
	os.Exit(1)
}

func forceCookieSession(scraper *twitterscraper.Scraper) {
	value := reflect.ValueOf(scraper).Elem()
	setPrivateBool(value.FieldByName("isLogged"), true)
	setPrivateString(
		value.FieldByName("bearerToken"),
		"AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
	)
}

func setPrivateBool(field reflect.Value, value bool) {
	reflect.NewAt(field.Type(), unsafe.Pointer(field.UnsafeAddr())).Elem().SetBool(value)
}

func setPrivateString(field reflect.Value, value string) {
	reflect.NewAt(field.Type(), unsafe.Pointer(field.UnsafeAddr())).Elem().SetString(value)
}
