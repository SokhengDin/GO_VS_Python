package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
	"github.com/google/uuid"
)

type Pets struct {
	ent.Schema
}

func (Pets) Fields() []ent.Field {
	return []ent.Field{
		field.UUID("id", uuid.UUID{}).Default(uuid.New),
		field.UUID("user_id", uuid.UUID{}),
		field.String("name"),
		field.String("type"),
		field.Bool("is_active").Default(true),
	}
}

func (Pets) Edges() []ent.Edge {
	return []ent.Edge{
		edge.From("owner", Users.Type).
			Ref("pets").
			Unique(),
	}
}
