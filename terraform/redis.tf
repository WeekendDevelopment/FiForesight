resource "upstash_redis_database" "redis" {
  database_name  = "fiforesight-redis"
  primary_region = "eu-west-2"
  tls            = true
  region         = "global"
}

output "redis_rest_url" {
  description = "Upstash Redis REST endpoint (used by upstash-redis Python SDK)"
  value       = "https://${upstash_redis_database.redis.endpoint}"
}

output "redis_rest_token" {
  description = "Upstash Redis REST token"
  value       = upstash_redis_database.redis.rest_token
  sensitive   = true
}
