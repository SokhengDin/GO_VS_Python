package schema

import (
	"entgo.io/ent"
	"entgo.io/ent/schema/edge"
	"entgo.io/ent/schema/field"
	"github.com/google/uuid"
)

type Users struct {
	ent.Schema
}

func (Users) Fields() []ent.Field {
	return []ent.Field{
		field.UUID("id", uuid.UUID{}).Default(uuid.New),
		field.String("name"),
		field.String("first_name"),
		field.String("last_name"),
		field.Bool("is_active").Default(true),
	}
}

func (Users) Edges() []ent.Edge {
	return []ent.Edge{
		edge.To("pets", Pets.Type),
	}
}
