resource "upstash_redis_database" "redis" {
  database_name  = "fiforesight-redis"
  primary_region = "eu-west-2"
  tls            = true
  region         = "global"
}

output "redis_url" {
  description = "Upstash Redis native connection URL (rediss://)"
  value       = "rediss://default:${upstash_redis_database.redis.password}@${upstash_redis_database.redis.endpoint}:${upstash_redis_database.redis.port}"
  sensitive   = true
}
